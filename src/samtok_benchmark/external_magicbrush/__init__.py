"""MagicBrush evaluation: public inputs, native editors and free reference metrics."""

DATASET = "osunlp/MagicBrush"
REVISION = "6c254560879df7851233ea0fd2ae2a62764d0ef2"
OFFICIAL_COMMIT = "d2d7f84d71ff23154e3f16f0c8f19392782bd201"
METHOD_COMMIT = "aa5a414e36c01eba60b37fc46cb9e32f803f8a93"
MODELS = ("sitedit", "qwen21", "qwen2511", "replan", "mirage", "flux3", "mice", "flux2_klein9b")
TRACKS = ("mask-free", "mask-provided")
NUM_SESSIONS, NUM_TURNS = 535, 1053
