{
  description = "eVOLVER hardware server — socket.io daemon + integrated workspace flake";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    evolver-arduino = {
      url = "github:pbert5/evolver-arduino";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    evolver-dpu = {
      url = "github:pbert5/dpu";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      evolver-arduino,
      evolver-dpu,
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      # ---- Packages ----

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

      # ---- Apps (runnable with nix run .#<name>) ----

      apps = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          serverPython = pkgs.python3.withPackages (
            ps: with ps; [
              pyserial
              python-socketio
              pyyaml
              requests
              six
              websocket-client
            ]
          );

          run-server = pkgs.writeShellApplication {
            name = "run-server";
            runtimeInputs = [ serverPython ];
            text = ''
              exec ${self.packages.${system}.evolver}/bin/evolver-server "$@"
            '';
          };

          run-virtual-evolver = pkgs.writeShellApplication {
            name = "run-virtual-evolver";
            text = ''
              export EVOLVER_OUTPUT_MODE="''${EVOLVER_OUTPUT_MODE:-virtual}"
              exec ${run-server}/bin/run-server "$@"
            '';
          };

          discover-devices = pkgs.writeShellApplication {
            name = "discover-devices";
            runtimeInputs = [
              (pkgs.python3.withPackages (ps: [
                ps.pyserial
                ps.pyyaml
              ]))
            ];
            text = ''
              set -euo pipefail
              REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
              # Run from repo root so evolver package is on PYTHONPATH
              exec python -c "
import sys, json
sys.path.insert(0, '${./.}')
from evolver.serial_discovery import discover_devices, list_serial_ports
results = discover_devices()
if not results:
    print('No serial ports found.')
else:
    for port, r in results.items():
        dev_id = r.hello.device_id if r.hello else 'n/a'
        print(f'{port}  {r.state.value}  {dev_id}')
" "$@"
            '';
          };

          provision-device = pkgs.writeShellApplication {
            name = "provision-device";
            runtimeInputs = [
              (pkgs.python3.withPackages (ps: [
                ps.pyserial
                ps.pyyaml
              ]))
            ];
            text = ''
              set -euo pipefail
              PORT="''${PORT:-}"
              DEVICE_ID="''${DEVICE_ID:-}"
              OWNER_ID="''${OWNER_ID:-}"

              if [ -z "$PORT" ] || [ -z "$DEVICE_ID" ] || [ -z "$OWNER_ID" ]; then
                echo "Usage: PORT=/dev/ttyACM0 DEVICE_ID=mev-001 OWNER_ID=server-xyz nix run .#provision-device"
                exit 1
              fi

              echo "WARNING: This will write identity to $PORT."
              echo "  device_id: $DEVICE_ID"
              echo "  owner_id:  $OWNER_ID"
              printf "Continue? [y/N] "
              read -r confirm
              case "$confirm" in [yY]*) ;; *) echo "Aborted."; exit 1 ;; esac

              python -c "
import sys
sys.path.insert(0, '${./.}')
import serial
from evolver.provisioning import ProvisioningStateMachine, ProvisioningMode, DeviceState
sm = ProvisioningStateMachine(mode=ProvisioningMode.ASK)
with serial.Serial('$PORT', 9600, timeout=5) as conn:
    result = sm.identify(conn)
    print(f'Device state: {result.state.value}')
    if result.state != DeviceState.UNPROVISIONED:
        print('ERROR: device is not UNPROVISIONED. Use CLEAR_ID first if you need to reprovision.')
        sys.exit(1)
with serial.Serial('$PORT', 9600, timeout=5) as conn:
    sm2 = ProvisioningStateMachine(mode=ProvisioningMode.AUTO)
    sm2.provision(conn, '$DEVICE_ID', '$OWNER_ID')
    print('Provisioned successfully.')
"
            '';
          };

          export-calibration = pkgs.writeShellApplication {
            name = "export-calibration";
            runtimeInputs = [
              (pkgs.python3.withPackages (ps: [
                ps.pyserial
                ps.pyyaml
              ]))
            ];
            text = ''
              set -euo pipefail
              OUT="''${OUT:-device-export.json}"
              DEVICE_ID="''${DEVICE_ID:-}"
              SERVER_ID="''${SERVER_ID:-}"

              if [ -z "$DEVICE_ID" ] || [ -z "$SERVER_ID" ]; then
                echo "Usage: DEVICE_ID=mev-001 SERVER_ID=server-xyz [OUT=export.yaml] nix run .#export-calibration"
                exit 1
              fi

              python -c "
import sys, json
sys.path.insert(0, '${./.}')
from evolver.identity_store import DeviceExport, CalibrationData
import os, json
# Load calibrations.json if present
cal_path = os.environ.get('EVOLVER_DATA_DIR', '.') + '/calibrations.json'
cal_data = {}
if os.path.exists(cal_path):
    with open(cal_path) as f:
        cal_data = json.load(f)
e = DeviceExport(
    server_id='$SERVER_ID',
    device_id='$DEVICE_ID',
    calibration=CalibrationData(od=cal_data.get('od', {}),
                                temperature=cal_data.get('temp', {}),
                                pumps=cal_data.get('pump', {})),
    metadata={'source': 'export-calibration nix app'},
)
e.save('$OUT')
print(f'Exported to $OUT')
"
            '';
          };
        in
        {
          "run-server" = {
            type = "app";
            program = "${run-server}/bin/run-server";
          };
          "run-virtual-evolver" = {
            type = "app";
            program = "${run-virtual-evolver}/bin/run-virtual-evolver";
          };
          "discover-devices" = {
            type = "app";
            program = "${discover-devices}/bin/discover-devices";
          };
          "provision-device" = {
            type = "app";
            program = "${provision-device}/bin/provision-device";
          };
          "export-calibration" = {
            type = "app";
            program = "${export-calibration}/bin/export-calibration";
          };
          # Forwarded from evolver-arduino
          "build-firmware" = evolver-arduino.apps.${system}."build-firmware";
          "upload-firmware" = evolver-arduino.apps.${system}."upload-firmware";
          "setup-arduino" = evolver-arduino.apps.${system}."setup-arduino";
          # Forwarded from evolver-dpu
          "run-dpu" = evolver-dpu.apps.${system}."run-dpu";

          default = {
            type = "app";
            program = "${run-server}/bin/run-server";
          };
        }
      );

      # ---- Checks ----

      checks = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          lintPython = if pkgs ? python36 then pkgs.python36 else pkgs.python3;
          testPython = pkgs.python3.withPackages (ps: [
            ps.pytest
            ps.pyserial
            ps.pyyaml
          ]);
        in
        {
          lint = pkgs.runCommand "flake8-lint" {
            nativeBuildInputs = [ (lintPython.withPackages (ps: [ ps.flake8 ])) ];
            src = ./evolver;
          } ''
            flake8 --select=E9,F63,F7,F82 --ignore=F824 --exclude=$src/socketIO_client $src
            touch $out
          '';

          provisioning-tests = pkgs.runCommand "provisioning-tests" {
            nativeBuildInputs = [ testPython ];
            src = ./.;
          } ''
            cp -r "$src/evolver" evolver
            cp -r "$src/tests" tests
            touch evolver/__init__.py tests/__init__.py
            PYTHONPATH="$PWD:$PWD/evolver" pytest tests/ -v --ignore=tests/hardware
            touch $out
          '';
        }
      );

      # ---- Dev Shells ----

      devShells = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          devPython = if pkgs ? python36 then pkgs.python36 else pkgs.python3;
        in
        {
          # Full integrated workspace shell
          default = pkgs.mkShell {
            name = "evolver-workspace";
            packages = [
              (devPython.withPackages (
                ps: with ps; [
                  aiohttp
                  flake8
                  pyserial
                  python-socketio
                  pyyaml
                  pytest
                  requests
                  six
                  websocket-client
                ]
              ))
              pkgs.arduino-cli
              pkgs.poetry
            ];
            shellHook = ''
              echo "eVOLVER workspace dev shell"
              echo ""
              echo "Server:    nix run .#run-server"
              echo "Virtual:   nix run .#run-virtual-evolver"
              echo "DPU:       nix run .#run-dpu       (run from evolver-dpu/ dir)"
              echo "Firmware:  nix run .#build-firmware (run from evolver-arduino/ dir)"
              echo "Upload:    PORT=/dev/ttyACM0 nix run .#upload-firmware"
              echo "Discover:  nix run .#discover-devices"
              echo "Tests:     pytest tests/"
              echo ""
              echo "First-time arduino setup: nix run .#setup-arduino"
            '';
          };

          # Arduino-only shell (forwarded from sub-flake)
          arduino = evolver-arduino.devShells.${system}.default;

          # DPU-only shell (forwarded from sub-flake)
          dpu = evolver-dpu.devShells.${system}.default;
        }
      );

      # ---- NixOS Module ----

      nixosModules.evolver = import ./nix/evolver-module.nix;
      nixosModules.default = self.nixosModules.evolver;
    };
}
