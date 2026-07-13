{
  lib,
  pkgs,
  python3,
  stdenvNoCC,
  symlinkJoin,
  writeShellApplication,
}:
let
  pythonEnv = python3.withPackages (
    ps: with ps; [
      aiohttp
      pyserial
      python-socketio
      pyyaml
      requests
      six
      websocket-client
    ]
  );

  # evolver Python source. Runtime launchers initialise EVOLVER_DATA_DIR so
  # mutable state stays outside the read-only Nix store.
  evolverSrc = stdenvNoCC.mkDerivation {
    pname = "evolver-src";
    version = "0.0.0";
    src = lib.cleanSourceWith {
      src = ../evolver;
      filter =
        path: _type:
        let
          b = builtins.baseNameOf path;
        in
        !(builtins.elem b [
          "__pycache__"
          ".git"
        ]);
    };

    dontConfigure = true;
    dontBuild = true;

    installPhase = ''
      runHook preInstall
      mkdir -p "$out/share/evolver"
      cp -r . "$out/share/evolver/"
      runHook postInstall
    '';
  };

  # Launcher script: initialises the state directory on first run then starts
  # the server.  PYTHONPATH lets Python resolve evolver_server.py and
  # multi_server.py as sibling modules of evolver.py.
  evolverServer = writeShellApplication {
    name = "evolver-server";
    runtimeInputs = [ pythonEnv ];
    text = ''
      if [ -n "''${EVOLVER_DATA_DIR:-}" ]; then
        DATA_DIR="$EVOLVER_DATA_DIR"
      elif [ -n "''${XDG_STATE_HOME:-}" ]; then
        DATA_DIR="$XDG_STATE_HOME/evolver"
      elif [ -n "''${HOME:-}" ]; then
        DATA_DIR="$HOME/.local/state/evolver"
      else
        DATA_DIR="$PWD/.evolver-state"
      fi
      export EVOLVER_DATA_DIR="$DATA_DIR"
      export EVOLVER_MOCK_SERIAL="''${EVOLVER_MOCK_SERIAL:-auto}"

      mkdir -p "$DATA_DIR"

      # Copy default config/data files into the state dir on first run;
      # existing files are never overwritten so operator edits are preserved.
      for f in conf.yml calibrations.json evolver-config.json test_device.json; do
        src="${evolverSrc}/share/evolver/$f"
        dst="$DATA_DIR/$f"
        if [ -f "$src" ] && [ ! -f "$dst" ]; then
          cp "$src" "$dst"
        fi
        if [ -f "$dst" ]; then
          chmod u+w "$dst"
        fi
      done

      export PYTHONPATH="${evolverSrc}/share/evolver''${PYTHONPATH:+:$PYTHONPATH}"
      exec python "${evolverSrc}/share/evolver/evolver.py" "$@"
    '';
  };
in
symlinkJoin {
  name = "evolver";
  paths = [
    evolverSrc
    evolverServer
  ];
  meta = {
    description = "eVOLVER server — hardware control daemon for the eVOLVER continuous culture platform";
    homepage = "https://github.com/FYNCH-BIO/evolver";
    license = lib.licenses.mit;
    mainProgram = "evolver-server";
    platforms = lib.platforms.linux;
  };
}
