# Continuous training improvement battery

This experiment compares six compact candidates using identical model
source, initial weights, oracle data, scenario seeds, and six-second
evaluation horizons. It remains separate from the formal safety certificate.

The candidates are behavior cloning with MSE; Huber cloning with low Gaussian
variance; Huber cloning with low variance and a Gaussian mean constrained to
the actuator's useful +/-10 V range; Huber cloning followed by shielded
proposal-credit PPO; and bounded Huber cloning followed by unshielded PPO that
terminates on physical prohibitions. The sixth candidate removes the GRU and
trains a plain feed-forward actor-critic from scratch with shielded
proposal-credit PPO. It is an architecture ablation: no oracle cloning and no
state is carried between control steps.

The bounded-mean actor does not clip sampled actions after sampling. It
parameterizes the Gaussian mean through `10*tanh(raw_mean/10)`, so the
distribution retains a valid Gaussian log probability. Evaluation reports
both shielded task behavior and unshielded task/safety behavior for every
candidate. No checkpoint is marked deployable.
