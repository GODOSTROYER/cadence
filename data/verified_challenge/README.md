# Challenge packet: 80 synthetic boundary cases

Read the [shared annotation guide](../verified_sampling/README.md) and [prospective policy v2](../../docs/POLICY_V2.md) before labeling. The exact policy is frozen in [policy.snapshot.yaml](policy.snapshot.yaml).

Complete [human_labels.csv](human_labels.csv) from the text, policy and any `scenario_setup` alone, before model inference. Preserve `id`, `text` and `scenario_setup`; save a separate `completed_human_labels.csv`. Follow the shared guide's named human import/validation commands. The current worksheet is blank and no human labels, reply ratings or inference are claimed.

All 80 cases were independently AI-authored by an Astra extra-high-reasoning author, with 10 cases in each of eight categories. These are synthetic boundary scenarios, not sampled customer messages or traffic prevalence. Operational controls are specified, not executed by preparing this packet. Two contrast pairs intentionally contain similar cases.

[SAMPLE.lock.json](SAMPLE.lock.json) binds the cases, policy, author identity and prior-exposure registry. The [authoring record](../verified_challenge_authored/AUTHORING.json) describes how the source scenarios were created. The final 200 natural confirmation cases are a separate partition.
