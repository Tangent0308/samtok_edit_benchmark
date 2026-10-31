"""IF-Bench tiered protocol, independent of the historical v2 runners."""

PROTOCOL = "ifbench-tiered-v1"
SCHEMA = "ifbench.public.v1"
SEED = 20261027
GENERATION_SEED = 42
SETTINGS = (
    "S1",
    "S2-point",
    "S2-box",
    "S2-mask",
    "S3-point",
    "S3-box",
    "S3-mask",
    "S4-ref",
    "S4-noref",
    "S5",
)
MODALITIES = ("point", "box", "mask")
MANIFEST_SHA256 = "818ce524a1d1f363dc8ea5caa7a887b2dd0355c17a5600d1cbd696cffcf263fb"
AUDIT_CASES = ("v2-sa_10063996", "v2-sa_10781767")
