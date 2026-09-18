# Calibration packet: 100 real corpus messages

Read the [shared annotation guide](../verified_sampling/README.md) and [prospective policy v2](../../docs/POLICY_V2.md) before labeling. The exact policy is frozen in [policy.snapshot.yaml](policy.snapshot.yaml).

[human_labels.csv](human_labels.csv) is an optional blank human-labeling worksheet. This partition is for calibration/development; AI labels must be explicitly attributed and must not be recorded as human work. No model inference or labels were produced during sampling.

[SAMPLE.lock.json](SAMPLE.lock.json) binds the sample, policy and exposure registry. Do not edit the locked examples or snapshots. This sample excludes recorded/reconstructed exposures; incomplete historical inspection records prevent a universal never-seen claim.
