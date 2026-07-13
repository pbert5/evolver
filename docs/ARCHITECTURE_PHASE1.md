# Integrated Architecture Phase 1

This phase introduces the first explicit boundaries for the local integrated
eVOLVER runtime without replacing the current server or DPU workflow.

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

Phase 1 implements the shared contracts and local service scaffolding:

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

## Next Steps

1. Add an adapter that converts existing server broadcasts into raw measurement
   envelopes.
2. Add a runner manager that launches the current DPU script as an isolated
   subprocess.
3. Expose the control-plane API over a local HTTP or Socket.IO service.
4. Move graphing reads from experiment directories to `LocalDataService`
   streams or standardized exports.
