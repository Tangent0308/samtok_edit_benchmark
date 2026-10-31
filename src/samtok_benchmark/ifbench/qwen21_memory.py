"""Opt-in native device placement; no changes to Qwen2.1 inference math or inputs."""

POLICIES = ("resident", "model_cpu_offload")
NATIVE_OFFLOAD_SEQUENCE = "text_encoder->transformer->vae"


def validate_memory_policy(policy):
    if policy not in POLICIES:
        raise ValueError(f"Unsupported Qwen2.1 memory policy: {policy!r}")
    return policy


def place_pipeline(pipe, policy="resident"):
    """Load on CPU first, then use the selected official placement API.

    Do not move the full pipeline to CUDA before enabling model CPU offload.
    Accelerate moves the predecessor transformer off the GPU at VAE decode;
    the native local KV cache is deliberately left intact.
    """
    validate_memory_policy(policy)
    if policy == "model_cpu_offload":
        if pipe.model_cpu_offload_seq != NATIVE_OFFLOAD_SEQUENCE:
            raise ValueError("Pinned Qwen2.1 native CPU offload sequence changed")
        pipe.enable_model_cpu_offload(gpu_id=0, device="cuda")
    else:
        pipe = pipe.to("cuda")
    return pipe, {
        "memory_policy": policy,
        "native_cpu_offload_sequence": NATIVE_OFFLOAD_SEQUENCE
        if policy == "model_cpu_offload"
        else None,
        "vae_tiling_enabled_by_adapter": False,
        "precision_changed_by_adapter": False,
    }
