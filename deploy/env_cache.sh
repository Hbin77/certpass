# 팀 서버 캐시 경로를 /data 아래로(운영진 안내 2026-11-07 19:18: 소스·데이터·모델 학습/추론 캐시를 /data에서 관리)
export XDG_CACHE_HOME=/data/.cache
export UV_CACHE_DIR=/data/.cache/uv
export PIP_CACHE_DIR=/data/.cache/pip
export TORCH_HOME=/data/.cache/torch
export HF_HOME=/data/.cache/huggingface
export MPLCONFIGDIR=/data/.cache/matplotlib
export CUDA_CACHE_PATH=/data/.nv/ComputeCache
export PATH=/data/tools:$PATH
