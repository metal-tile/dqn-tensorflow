#!/usr/bin/env bash

ENV_NAME="CartPole-v1"

python -m trainer.task --output_path outputs/${ENV_NAME} \
                       --n_episodes 5000 \
                       --learning_rate 0.001 \
                       --n_updates 20 \
                       --batch_size 100 \
                       --env_name ${ENV_NAME}
