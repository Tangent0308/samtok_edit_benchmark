"""Additional native baselines on an unchanged, previously frozen validation cohort."""

ADDITIONAL = {
    "compbench": ("flux2_klein9b", "mice", "replan"),
    "interedit": ("flux2_klein9b", "mice"),
    "omni_iie": ("flux2_klein9b", "mice"),
}
REUSED = ("qwen21", "sitedit")
MODELS = ("flux2_klein9b", "mice", "replan")
