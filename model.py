from __future__ import absolute_import
from __future__ import division
from __future__ import print_function


import tensorflow as tf
import numpy as np

import model

from slim.nets import inception_v2
from nets import googLeNet

slim = tf.contrib.slim

NUM_SUB_RANGE = 5



def FCN(inputs, scope):
    """
    Raw View Descriptor Generation

    Extract the raw view descriptors. Compared with deeper CNN,
    shallow FCN could have more position information,
    which is needed for the followed grouping module.
    and the deeper CNN will have the content information which could
    represent the view feature better.

    Args:
    inputs: N x V x H x W x C tensor

    Returns:
    tensor_outs: list of output tensor corresponding to the final_endpoint.
    # end_points: a set of activations for external use, for example summaries or
    #             losses.

    """

    n_views = inputs.get_shape().as_list()[1]

    # transpose views: (NxVxHxWxC) -> (VxNxHxWxC)
    views = tf.transpose(inputs, perm=[1, 0, 2, 3, 4])

    input_views = []
    raw_view_descriptors = []  # Raw View Descriptors
    for i in range(n_views):

        view = tf.gather(views, i)  # NxWxHxC

        net, end_points = inception_v2.inception_v2_base(view, scope=scope)

        input_views.append(view)
        raw_view_descriptors.append(net)

    return input_views, raw_view_descriptors, end_points



'''
CNN is the same as GoogLeNet.

Inception. v1. (a.k.a GoogLeNet)
'''
def CNN():

    return

#
# def true_fn(n_range, group, input_views, i):
#     group[str(n_range) + "_group_scheme"].append(input_views[i])
#     return
#
# def false_fn(n_range, group, input_views, i):
#     return


def grouping_weight_scheme(input_views, discrimination_scores):
    group = {}
    for i in range(NUM_SUB_RANGE):
        group[str(i) + "_group_scheme"] = []

    g0 = tf.constant(0, dtype=tf.float32)
    g1 = tf.constant(0.2, dtype=tf.float32)
    g2 = tf.constant(0.4, dtype=tf.float32)
    g3 = tf.constant(0.6, dtype=tf.float32)
    g4 = tf.constant(0.8, dtype=tf.float32)
    g5 = tf.constant(1, dtype=tf.float32)

    def fn1(g, i):
        group[str(g) + "_group_scheme"].append(input_views[i])
        return tf.constant(1)
        # return

    for i, score in enumerate(discrimination_scores):
        # tf.case(
        #     pred_fn_pairs=[
        #         ((tf.greater_equal(score, g0) & tf.less(score, g1)), lambda: fn1(0, i)),
        #         ((tf.greater_equal(score, g1) & tf.less(score, g2)), lambda: fn1(1, i)),
        #         ((tf.greater_equal(score, g2) & tf.less(score, g3)), lambda: fn1(2, i)),
        #         ((tf.greater_equal(score, g3) & tf.less(score, g4)), lambda: fn1(3, i)),
        #         ((tf.greater_equal(score, g4) & tf.less(score, g5)), lambda: fn1(4, i))],
        #     default=None,
        #     exclusive=False)
        tf.case(
            pred_fn_pairs=[
                (tf.logical_and(tf.greater_equal(score, g0), tf.less(score, g1)), lambda: fn1(0, i)),
                (tf.logical_and(tf.greater_equal(score, g1), tf.less(score, g2)), lambda: fn1(1, i)),
                (tf.logical_and(tf.greater_equal(score, g2), tf.less(score, g3)), lambda: fn1(2, i)),
                (tf.logical_and(tf.greater_equal(score, g3), tf.less(score, g4)), lambda: fn1(3, i)),
                (tf.logical_and(tf.greater_equal(score, g4), tf.less(score, g5)), lambda: fn1(4, i))],
            default=None,
            exclusive=True)

    return group



def grouping_module(input_views,
                    raw_view_descriptors,
                    end_points,
                    num_classes,
                    reuse=None,
                    scope='InceptionV2',
                    global_pool=True,
                    spatial_squeeze=True,
                    dropout_keep_prob=0.8):
    """
    The grouping module aims to learn the group information
    to assist in mining the relationship among views.

    Args:
    input_views: N x H x W x C tensor

    :return:
    """

    discrimination_scores = []
    for i, net in enumerate(raw_view_descriptors):
        with tf.variable_scope('Logits'):
            if global_pool:
                # Global average pooling.
                net = tf.reduce_mean(net, [1, 2], keep_dims=True, name='global_pool')
                end_points['global_pool'] = net
            else:
                # Pooling with a fixed kernel size.
                kernel_size = inception_v2._reduced_kernel_size_for_small_input(net, [7, 7])
                net = slim.avg_pool2d(net, kernel_size, padding='VALID',
                                      scope='AvgPool_1a_{}x{}'.format(*kernel_size))
                end_points['AvgPool_1a'] = net
            # if not num_classes:
            #     return net, end_points

            # 1 x 1 x 1024
            net = slim.dropout(net, dropout_keep_prob, scope='Dropout_1b')
            net = slim.flatten(net)
            # net = slim.fully_connected(net, 512)
            logits = slim.fully_connected(net, 1, activation_fn=None)

            # logits = slim.conv2d(net, num_classes, [1, 1], activation_fn=None,
            #                      normalizer_fn=None, scope='Conv2d_0c_1x1')
            # if spatial_squeeze:
            #     logits = tf.squeeze(logits, [1, 2], name='SpatialSqueeze')
            end_points['Logits'] = logits
            # end_points['Predictions'] = prediction_fn(logits, scope='Predictions')
            score = tf.nn.sigmoid(tf.log(tf.abs(logits)))
            score = tf.reshape(score, [])
            discrimination_scores.append(score)


    # grouping weight/scheme
    group = grouping_weight_scheme(input_views, discrimination_scores)






    return discrimination_scores, group


# def view_pooling():
#
#
#
#
#
# def group_fusion():
#     return


def gvcnn(inputs,
          num_classes=1000,
          reuse=tf.AUTO_REUSE,
          is_training=True,
          scope='InceptionV2',
          global_pool=True,
          spatial_squeeze=True,
          dropout_keep_prob=0.8):

    """
    Args:
    inputs: a tensor of shape [batch_size, views, height, width, channels].
    """

    with tf.variable_scope(scope, 'InceptionV2', [inputs], reuse=reuse) as scope:
        with slim.arg_scope([slim.batch_norm, slim.dropout],
                            is_training=is_training):
            input_views, raw_view_descriptors, end_points = model.FCN(inputs, scope)
            discrimination_scores, group = model.grouping_module(input_views,
                                                          raw_view_descriptors,
                                                          end_points,
                                                          num_classes,
                                                          reuse,
                                                          scope)


    # Final View Descriptors -> View Pooling

    return discrimination_scores, group