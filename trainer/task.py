# -*- coding: utf-8 -*-

# Default modules
import argparse
import json
import os

import numpy as np
import tensorflow as tf

from trainer import dqn, repmem
from trainer import chasing

N_INPUTS = 5
N_EPOCH = 5000
LEARNING_RATE = 1e-4
N_ACTIONS = 5
N_KERNEL = 2

# Set log level
tf.logging.set_verbosity(tf.logging.DEBUG)

# Parse arguments
parser = argparse.ArgumentParser()
parser.add_argument("--output_path", type=str)
args, unknown_args = parser.parse_known_args()
tf.logging.info("known args: {}".format(args))

# Get environment variable for Cloud ML
tf_conf = json.loads(os.environ.get("TF_CONFIG", "{}"))
# For local
if not tf_conf:
    tf_conf = json.load(open("local.json"))
tf.logging.debug("TF_CONF: {}".format(json.dumps(tf_conf)))

# Cluster setting for cloud
cluster = tf_conf.get("cluster", None)

server = tf.train.Server(
    cluster,
    job_name=tf_conf["task"]["type"],
    task_index=tf_conf["task"]["index"]
)

# Parameter server
if tf_conf["task"]["type"] == "ps":
    server.join()
# Master and workers
else:
    device_fn = tf.train.replica_device_setter(
        cluster=tf.train.ClusterSpec(cluster=cluster),
        worker_device="/job:{0}/task:{1}".format(tf_conf["task"]["type"], tf_conf["task"]["index"]),
    )

    # Logging
    tf.logging.debug("/job:{0}/task:{1} build graph".format(tf_conf["task"]["type"], tf_conf["task"]["index"]))

    # Build graph
    with tf.Graph().as_default() as graph:
        with tf.device(device_fn):
            # Create DQN agent
            dqn_agent = dqn.DQN(input_size=N_INPUTS, learning_rate=LEARNING_RATE, n_actions=N_ACTIONS)
            global_step = tf.Variable(0, trainable=False, name="global_step")
            init_op = tf.initialize_all_variables()
            # Create saver
            saver = tf.train.Saver(max_to_keep=10)

    # Create game simulator
    game_simulator = chasing.ChasingSimulator(field_size=N_INPUTS)
    # Create replay memory
    replay_memory = repmem.ReplayMemory()

    sv = tf.train.Supervisor(
        graph=graph,
        is_chief=(tf_conf["task"]["type"] == "master"),
        logdir=args.output_path,
        init_op=init_op,
        global_step=global_step,
        summary_op=None
    )

    with sv.managed_session(server.target) as sess:
        # Create summary writer
        summary_writer = tf.train.SummaryWriter(args.output_path, graph=sess.graph)
        # Initializer
        sess.run(init_op)
        win_count = 0
        for i in range(N_EPOCH):
            # Play a new game
            while not game_simulator.terminal:
                # Act at random on the first few games
                if i < 100:
                    action = np.random.randint(N_ACTIONS)
                # Act at random with a fixed probability
                elif np.random.uniform() >= 0.9:
                    action = np.random.randint(N_ACTIONS)
                # Act following the policy on the other games
                else:
                    action = np.argmax(dqn_agent.act(sess, np.array([x_t])))
                # Act on the game simulator
                res = game_simulator.input_key(action)
                # Receive the results from the game simulator
                x_t = res["state_prev"]
                x_t_plus_1 = res["state"]
                terminal = res["terminal"]
                r_t = res["reward"]
                a_t = res["action"]
                if i == 0 or r_t > 0.5:
                    replay_memory.store(x_t, a_t, r_t, x_t_plus_1, terminal)
                # Update the policy
                mini_batch = replay_memory.sample(size=32)
                train_loss = dqn_agent.update(
                    sess,
                    mini_batch["s_t"],
                    mini_batch["a_t"],
                    mini_batch["r_t"],
                    mini_batch["s_t_plus_1"],
                    mini_batch["terminal"]
                )
            tf.logging.info("epoch: {0} win_rate: {1} reward: {2} loss: {3}".format(
                i, win_count/(i+1e-5), r_t, np.mean(train_loss))
            )
            if r_t > 0.5:
                win_count += 1
            game_simulator.init_game()
        # Save model
        dqn_agent.save_model(sess, args.output_path)
        sv.stop()
