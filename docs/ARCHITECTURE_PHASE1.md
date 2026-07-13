# Integrated Architecture Phases

These phases introduce explicit boundaries for the local integrated eVOLVER
runtime without replacing the current server or DPU workflow all at once.

## Services

The intended local process layout is:

```text
supervisor
├── evolver-hardwared
├── evolver-controld
├── evolver-datad
├── evolver-ui
└── evolver-syncd
```

Phase 1 implemented the shared contracts and local service scaffolding:

- `evolver.messages` defines versioned envelopes and validation helpers.
- `evolver.data_service.LocalDataService` writes append-only JSONL streams.
- `evolver.control_plane.ControlPlane` owns experiment lifecycle state and
  validates runner actions before forwarding device commands.

## Boundaries

Only the hardware service should own serial communication. Experiment runners
and user interfaces send requests to the control plane, and the control plane
validates those requests before handing low-level commands to the hardware
client.

Raw measurements are written independently of experiment processing:

```text
eVOLVER server -> raw measurement envelope -> LocalDataService
```

Experiment runners submit actions through an envelope:

```text
runner -> experiment.runner.action -> ControlPlane -> hardware client
```

## Compatibility

The phase-1 command schema accepts the existing DPU command shape:

```json
{
  "param": "temp",
  "value": ["NaN", "3001"],
  "immediate": true,
  "recurring": false,
  "fields_expected_outgoing": 17,
  "fields_expected_incoming": 17
}
```

This allows the current DPU code to be wrapped as a managed subprocess in a
later phase rather than rewritten immediately.

## Phase 2: Raw Ingestion

`evolver.broadcast_ingest.BroadcastIngestor` converts the current Socket.IO
broadcast shape into `machine.measurement.raw` envelopes and writes them through
`LocalDataService`.

This keeps durable raw-data capture independent from experiment scripts,
graphing, and UI clients.

## Phase 3: Runner Isolation

`evolver.runner_manager.DpuRunnerManager` launches the current DPU
`experiment/template/eVOLVER.py` script as a subprocess. This preserves the
existing DPU behavior while giving the control plane a place to track runner
state, interrupt a runner, and stop it without loading user code into the
control-plane process.

## Phase 4: Local Control API

`evolver.control_api.create_control_plane_app` exposes a small aiohttp
application for local clients:

- `GET /health`
- `GET /experiments`
- `POST /experiments`
- `POST /experiments/{experiment_id}/start`
- `POST /experiments/{experiment_id}/pause`
- `POST /experiments/{experiment_id}/resume`
- `POST /experiments/{experiment_id}/stop`
- `POST /device-commands`
- `GET /jobs`

The API is intentionally thin. It delegates policy and validation to
`ControlPlane` instead of duplicating lifecycle rules in handlers.

`nix run .#run-control-plane` starts this API as a local service.

## Phase 5: Maintenance Jobs

`evolver.maintenance_jobs.MaintenanceJobManager` tracks controlled one-shot
operations such as calibration, firmware flashing, provisioning, diagnostics,
export, and sync. Jobs can require authorization before they move to `queued`,
and every state transition can be recorded through `LocalDataService`.

`nix run .#run-broadcast-ingest` subscribes to the existing eVOLVER Socket.IO
server and persists broadcasts through the phase-2 ingestor.

## Remaining Integration Work

1. Decide whether raw ingestion should remain a subscribed local client or move
   directly inside the hardware server process.
2. Promote `run-control-plane` and `run-broadcast-ingest` from Nix apps into
   systemd-supervised services for dedicated console installs.
3. Let full experiment creation workflows supply finalized runner
   configuration to `DpuRunnerManager`.
4. Move graphing reads from experiment directories to `LocalDataService`
   streams or standardized exports.
5. Add systemd supervision for the new processes.
