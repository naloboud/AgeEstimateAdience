import os
import numpy as np
import datetime
import time

import tensorflow as tf
import data_helper

#from gilnet import gilnet
#from alexnet import alexnet
from vggface import VGGFace

# Parameters settings
# Data loading params
tf.flags.DEFINE_string("dataset_file", "faces_dataset.h5", "Path for the h5py dataset.")
tf.flags.DEFINE_integer("folder_to_test", 1, "No. of folder to be tested (default: 1)")

# Model Hyperparameters
tf.flags.DEFINE_float("dropout_keep_prob", 0.5, "Dropout keep probability (default: 0.5)")
tf.flags.DEFINE_float("weight_decay", 1e-3, "Weight decay rate for L2 regularization (default: 5e-4)")

# Training Parameters
tf.flags.DEFINE_float("learning_rate", 1e-3, "Starter Learning Rate (default: 1e-2)")
tf.flags.DEFINE_integer("batch_size", 64, "Batch Size (default: 128)")
tf.flags.DEFINE_integer("num_epochs", 50, "Number of training epochs (default: 200)")
tf.flags.DEFINE_integer("evaluate_every", 20, "Evaluate model on dev set after this many steps (default: 50)")
tf.flags.DEFINE_boolean("enable_moving_average", True, "Enable usage of Exponential Moving Average (default: True)")

FLAGS = tf.flags.FLAGS
FLAGS._parse_flags()
print("Parameters:")
for attr, value in sorted(FLAGS.__flags.items()):
    print("{}={}".format(attr, value))
print("")


# Data Preparation
# Load data
print("Loading data...")
train_data, train_label, test_data, test_label, bgr_mean = data_helper.load_dataset(FLAGS.dataset_file, FLAGS.folder_to_test)
# bgr_mean, mean_img
bgr_mean = [round(x, 4) for x in bgr_mean]

# ConvNet
acc_list = [0]
loss_train_list = [0]
loss_test_list = [0]

sess = tf.Session()

# Gilnet
#cnn = gilnet(bgr_mean=bgr_mean, 
#weight_decay=FLAGS.weight_decay, 
#enable_moving_average=FLAGS.enable_moving_average)

# AlexNet
#cnn = alexnet(bgr_mean=bgr_mean, 
#weight_decay=FLAGS.weight_decay, 
#enable_moving_average=FLAGS.enable_moving_average)

# VGGFace
cnn = VGGFace(bgr_mean=[93.5940, 104.7624, 129.1863], 
weight_decay=FLAGS.weight_decay, 
enable_moving_average=FLAGS.enable_moving_average,
weight_file="vggface_weights.npz")
vgg_known_acc_max = [0.65, 0.51, 0.59, 0.49, 0.59]

# Optimizer and LR Decay
global_step = tf.Variable(0, name="global_step", trainable=False)
optimizer = tf.train.MomentumOptimizer(FLAGS.learning_rate, 0.9)
lr_decay_fn = lambda lr, global_step : tf.train.exponential_decay(lr, global_step, 100, 0.95, staircase=True)
train_op = tf.contrib.layers.optimize_loss(loss=cnn.loss, global_step=global_step, clip_gradients=4.0,
	learning_rate=FLAGS.learning_rate, optimizer=lambda lr: optimizer, learning_rate_decay_fn=lr_decay_fn)
#grads_and_vars = optimizer.compute_gradients(cnn.loss)
#train_op = optimizer.apply_gradients(grads_and_vars, global_step=global_step)

# Checkpoint directory. 
# Tensorflow assumes this directory already exists so we need to create it
timestamp = str(int(time.time()))
out_dir = os.path.join(os.path.expanduser('~'), 'volume', "runs", timestamp)
print("Writing to {}\n".format(out_dir))
checkpoint_dir = os.path.abspath(os.path.join(out_dir, "checkpoints"))
checkpoint_prefix = os.path.join(checkpoint_dir, "model")
if not os.path.exists(checkpoint_dir):
	os.makedirs(checkpoint_dir)
saver = tf.train.Saver(tf.global_variables(), max_to_keep=5)

# Initialize Graph
sess.run(tf.global_variables_initializer())

# Train Step and Test Step
def train_step(x_batch, y_batch):
	"""
	A single training step
	"""
	feed_dict = {cnn.input_x: x_batch, cnn.input_y: y_batch, cnn.dropout_keep_prob: FLAGS.dropout_keep_prob}
	_, step, loss, accuracy = sess.run([train_op, global_step, cnn.loss, cnn.accuracy], feed_dict)
	time_str = datetime.datetime.now().isoformat()
	print("{}: Step {}, Loss {:g}, Acc {:g}".format(time_str, step, loss, accuracy))

def test_step(x_batch, y_batch):
	"""
	Evaluates model on a dev set
	"""
	feed_dict = {cnn.input_x: x_batch, cnn.input_y: y_batch, cnn.dropout_keep_prob: 1.0}
	loss, preds = sess.run([cnn.loss, cnn.predictions], feed_dict)
	time_str = datetime.datetime.now().isoformat()
	return preds, loss

# Generate batches
train_batches = data_helper.batch_iter(list(zip(train_data, train_label)), FLAGS.batch_size, FLAGS.num_epochs)

# Training loop. For each batch...
for train_batch in train_batches:
	x_batch, y_batch = zip(*train_batch)
	train_step(x_batch, y_batch)
	current_step = tf.train.global_step(sess, global_step)
	# Testing loop
	if current_step % FLAGS.evaluate_every == 0:
		print("\nEvaluation:")
		i = 0
		index = 0
		sum_loss = 0
		test_batches = data_helper.batch_iter(list(zip(test_data, test_label)), FLAGS.batch_size, 1)
		y_preds = np.ones(shape=len(test_label), dtype=np.int)
		for test_batch in test_batches:
			x_test_batch, y_test_batch = zip(*test_batch)
			preds, test_loss = test_step(x_test_batch, y_test_batch)
			sum_loss += test_loss
			res = np.absolute(preds - np.argmax(y_test_batch, axis=1))
			y_preds[index:index+len(res)] = res
			i += 1
			index += len(res)

		time_str = datetime.datetime.now().isoformat()
		acc = np.count_nonzero(y_preds==0)/len(y_preds)
		acc_list.append(acc)
		print("{}: Evaluation Summary, Loss {:g}, Acc {:g}".format(time_str, sum_loss/i, acc))
		print("{}: Current Max Acc {:g} with in Iteration {}".format(time_str, max(acc_list), int(acc_list.index(max(acc_list))*FLAGS.evaluate_every)))

		if max(acc_list) > vgg_known_acc_max[FLAGS.folder_to_test - 1]:
			path = saver.save(sess, checkpoint_prefix, global_step=current_step)
			print("Saved current model checkpoint with max accuracy to {}\n".format(path))