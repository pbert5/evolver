{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.services.evolver;

  # Converts a device path like /dev/ttyAMA0 → dev-ttyAMA0 (systemd unit naming)
  deviceUnit =
    port:
    "${lib.replaceStrings [ "/" ] [ "-" ] (lib.removePrefix "/" port)}.device";
in
{
  options.services.evolver = {
    enable = lib.mkEnableOption "eVOLVER hardware server";

    package = lib.mkOption {
      type = lib.types.package;
      description = "The evolver package providing the evolver-server binary.";
    };

    serialPort = lib.mkOption {
      type = lib.types.str;
      default = "/dev/ttyAMA0";
      description = "Serial port connected to the eVOLVER Arduino (Raspberry Pi default: /dev/ttyAMA0).";
    };

    stateDir = lib.mkOption {
      type = lib.types.str;
      default = "/var/lib/evolver";
      description = ''
        Directory for mutable runtime files: conf.yml, calibrations.json,
        evolver-config.json.  Populated from package defaults on first start;
        operator edits are preserved across upgrades.
      '';
    };

    user = lib.mkOption {
      type = lib.types.str;
      default = "evolver";
      description = "System user account that runs the evolver server.";
    };

    group = lib.mkOption {
      type = lib.types.str;
      default = "evolver";
      description = "Primary group for the evolver service user.";
    };

    openFirewall = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Open the evolver socket.io TCP port (8081) in the firewall.";
    };
  };

  config = lib.mkIf cfg.enable {
    users.groups.${cfg.group} = { };

    users.users.${cfg.user} = {
      isSystemUser = true;
      group = cfg.group;
      # dialout provides access to /dev/ttyAMA0 and other serial devices
      extraGroups = [ "dialout" ];
      home = cfg.stateDir;
      createHome = false;
    };

    systemd.tmpfiles.rules = [
      "d ${cfg.stateDir} 0750 ${cfg.user} ${cfg.group} - -"
    ];

    networking.firewall.allowedTCPPorts = lib.optionals cfg.openFirewall [ 8081 ];

    systemd.services.evolver = {
      description = "eVOLVER hardware server";
      documentation = [ "https://github.com/FYNCH-BIO/evolver" ];

      # Wait for the serial device to be available before starting
      after = [
        "network.target"
        (deviceUnit cfg.serialPort)
      ];
      wants = [ (deviceUnit cfg.serialPort) ];
      wantedBy = [ "multi-user.target" ];

      environment = {
        EVOLVER_DATA_DIR = cfg.stateDir;
        EVOLVER_MOCK_SERIAL = "false";
        HOME = cfg.stateDir;
      };

      serviceConfig = {
        ExecStart = lib.getExe cfg.package;
        User = cfg.user;
        Group = cfg.group;
        WorkingDirectory = cfg.stateDir;

        # Automatic restart replaces the old supervisord + cron watchdog
        Restart = "on-failure";
        RestartSec = "10s";

        # Serial port access
        SupplementaryGroups = [ "dialout" ];

        # Sandboxing — keep it tight while allowing serial/network/state dir
        NoNewPrivileges = true;
        PrivateTmp = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        ReadWritePaths = [ cfg.stateDir ];
        DeviceAllow = [
          "char-tty rw"
          "${cfg.serialPort} rw"
        ];
      };
    };
  };
}
