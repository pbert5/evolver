{
  description = "eVOLVER hardware server — socket.io daemon that controls the eVOLVER continuous culture platform via serial";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
  };

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      # Installable package — the evolver-server binary bundled with its Python env
      packages = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          evolver = pkgs.callPackage ./nix/evolver-package.nix { };
          default = self.packages.${system}.evolver;
        }
      );

      # Critical Python check — run with: nix flake check
      # NOTE: python36 was removed from nixpkgs 23.05+. Pin nixpkgs to 22.11 or earlier if
      # you need the exact interpreter; otherwise python3 is used here for the lint env.
      # The upstream server code is legacy Python with many historical style
      # violations. Keep the flake check focused on parse errors and serious
      # pyflakes failures so it stays useful on modern nixpkgs.
      checks = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          # Target interpreter is Python 3.6 (evolver.py shebang); use python3 as fallback
          # when pkgs.python36 is unavailable (nixpkgs >= 23.05).
          lintPython = if pkgs ? python36 then pkgs.python36 else pkgs.python3;
        in
        {
          lint = pkgs.runCommand "flake8-lint" {
            nativeBuildInputs = [ (lintPython.withPackages (ps: [ ps.flake8 ])) ];
            src = ./evolver;
          } ''
            flake8 --select=E9,F63,F7,F82 --ignore=F824 --exclude=$src/socketIO_client $src
            touch $out
          '';
        }
      );

      # Dev shell for working on the evolver server code itself
      devShells = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          # Target: Python 3.6 (evolver.py shebang). python36 removed from nixpkgs >= 23.05.
          devPython = if pkgs ? python36 then pkgs.python36 else pkgs.python3;
        in
        {
          default = pkgs.mkShell {
            name = "evolver";
            packages = [
              (devPython.withPackages (
                ps: with ps; [
                  aiohttp
                  flake8
                  pyserial
                  python-socketio
                  pyyaml
                  requests
                  six
                  websocket-client
                ]
              ))
            ];
            shellHook = ''
              echo "evolver dev shell — Python $(python3 --version)"
              echo "Run:  cd evolver && python evolver.py"
              echo "Check: flake8 --select=E9,F63,F7,F82 --ignore=F824 --exclude=evolver/socketIO_client evolver/"
            '';
          };
        }
      );

      # NixOS module — drop-in systemd service replacing supervisord + cron watchdog
      nixosModules.evolver = import ./nix/evolver-module.nix;
      nixosModules.default = self.nixosModules.evolver;
    };
}
