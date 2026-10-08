#!/usr/bin/env bash
#SBATCH --job-name=fair-kim
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=08:00:00
#SBATCH --output=fair-kim.%j.out
#SBATCH --error=fair-kim.%j.err

set -euo pipefail
cd "$(dirname "$0")"
PYTHON=${PYTHON:-python3}
DATASET=${DATASET:-email}
OUTPUT_DIR=${OUTPUT_DIR:-results}
srun "$PYTHON" run_fair_kim.py --dataset "$DATASET" --output-dir "$OUTPUT_DIR"
