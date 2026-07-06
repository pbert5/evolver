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

      # Dev shell for working on the evolver server code itself
      devShells = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          default = pkgs.mkShell {
            name = "evolver";
            packages = [
              (pkgs.python3.withPackages (
                ps: with ps; [
                  aiohttp
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
              echo "Run: cd evolver && python evolver.py"
            '';
          };
        }
      );

      # NixOS module — drop-in systemd service replacing supervisord + cron watchdog
      nixosModules.evolver = import ./nix/evolver-module.nix;
      nixosModules.default = self.nixosModules.evolver;
    };
}
