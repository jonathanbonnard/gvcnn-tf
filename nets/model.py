from __future__ import absolute_import
from __future__ import division
from __future__ import print_function


import tensorflow as tf
import numpy as np
import math

from nets import inception_v3, resnet_v2

slim = tf.contrib.slim


# find best group count for accuracy?
def group_scheme(view_discrimination_score, num_group, num_views):
    '''
    Note that 1 ≤ M ≤ N because there may exist sub-ranges
    that have no views falling into it.
    '''
    schemes = np.full((num_group, num_views), 0, dtype=np.int)
    for idx, score in enumerate(view_discrimination_score):
        schemes[int(score*10), idx] = 1 # 10 group

    return schemes


# TODO: recheck the paper.
def group_weight(g_schemes):
    num_group = g_schemes.shape[0]
    num_views = g_schemes.shape[1]

    weights = np.zeros(shape=(num_group), dtype=np.float32)
    for i in range(num_group):
        n = 0
        sum = 0
        for j in range(num_views):
            if g_schemes[i][j] == 1:
                sum += g_schemes[i][j]
                n += 1

        if n != 0:
            weights[i] = sum / n

    return weights


def view_pooling(final_view_descriptors, group_scheme):

    '''
    Intra-Group View Pooling

    Final view descriptors are source of view pooling with grouping scheme.

    Given the view descriptors and the generated grouping information,
    the objective here is to conduct intra-group
    view pooling towards a group level description.

    the views in the same group have the similar discrimination,
    which are assigned the same weight.

    :param group_scheme:
    :param final_view_descriptors:
    :return: group_descriptors
    '''

    group_descriptors = {}
    dummy = tf.zeros_like(final_view_descriptors[0])

    scheme_list = tf.unstack(group_scheme)
    indices = [tf.squeeze(tf.where(elem), axis=1) for elem in scheme_list]
    for i, ind in enumerate(indices):
        view_descs = tf.cond(tf.greater(tf.size(ind), 0),
                            lambda : tf.gather(final_view_descriptors, ind),
                            lambda : tf.expand_dims(dummy, 0))
        # TODO: max pooling ??
        group_descriptors[i] = tf.reduce_mean(view_descs, axis=0)

    return group_descriptors


def group_fusion(group_descriptors, group_weight):
    '''
    To generate the shape level description, all these group
    level descriptors should be further combined.

    The groups containing more discriminative views contribute more to
    the final 3D shape descriptor D(S) than those containing less discriminative views.
    By using these hierarchical view-group-shape description framework,
    the important and discriminative visual content can be discovered in the group level,
    and thus emphasized in the shape descriptor accordingly.

    :param
    group_descriptors: dic {index: group_desc}
    group_weight:

    :return:
    '''
    group_weight_list = tf.unstack(group_weight)
    numerator = []
    for key, value in group_descriptors.items():
        numerator.append(tf.multiply(group_weight_list[key], group_descriptors[key]))

    denominator = tf.reduce_sum(group_weight_list)   # denominator
    shape_descriptor = tf.div(tf.add_n(numerator), denominator)

    return shape_descriptor


def fcn(inputs, num_classes, is_training=True,
        dropout_keep_prob=0.8, reuse=tf.compat.v1.AUTO_REUSE):
    """
        Raw View Descriptor Generation

        first part of the network (FCN) to get the raw descriptor in the view level.
        The “FCN” part is the top five convolutional layers of GoogLeNet.
        (mid-level representation)

        Extract the raw view descriptors.
        Compared with deeper CNN, shallow FCN could have more position information,
        which is needed for the followed grouping module and the deeper CNN will have
        the content information which could represent the view feature better.

        Args:
        inputs: N x V x H x W x C tensor
        scope:
        """
    view_discrimination_scores = []
    final_view_descriptors = []

    n_views = inputs.get_shape().as_list()[1]
    # transpose views: (NxVxHxWxC) -> (VxNxHxWxC)
    views = tf.transpose(inputs, perm=[1, 0, 2, 3, 4])
    for index in range(n_views):
        batch_view = tf.gather(views, index)  # N x H x W x C
        # with slim.arg_scope(inception_v3.inception_v3_arg_scope()):
        #     _, end_points = inception_v3.inception_v3(batch_view,
        #                                               num_classes=num_classes,
        #                                               is_training=is_training,
        #                                               dropout_keep_prob=dropout_keep_prob,
        #                                               reuse=reuse)
        with slim.arg_scope(resnet_v2.resnet_arg_scope()):
            _, end_points = resnet_v2.resnet_v2_50(batch_view,
                                                   num_classes=num_classes,
                                                   is_training=is_training,
                                                   reuse=reuse)

        # GAP layer to obtain the discrimination scores from raw view descriptors.
        raw = tf.keras.layers.GlobalAveragePooling2D()(end_points['resnet_v2_50/block3'])
        raw = tf.keras.layers.Dense(1)(raw)
        raw = tf.reduce_mean(raw)
        batch_view_score = tf.nn.sigmoid(tf.math.log(tf.abs(raw)))
        view_discrimination_scores.append(batch_view_score)
        final_view_descriptors.append(end_points['resnet_v2_50/block4'])

    return view_discrimination_scores, final_view_descriptors


def gvcnn(fcn_inputs,
          num_classes,
          group_scheme,
          group_weight):

    # TODO: checkpoint - debug
    # -----------------------------
    # Intra-Group View Pooling
    group_descriptors = view_pooling(fcn_inputs, group_scheme)
    # Group Fusion
    shape_descriptor = group_fusion(group_descriptors, group_weight)
    # -----------------------------

    # # for debug
    # shape_descriptor = tf.reduce_max(fcn_inputs, axis=0)

    net = tf.keras.layers.GlobalAveragePooling2D()(shape_descriptor)
    logits = tf.keras.layers.Dense(num_classes)(net)

    return shape_descriptor, logits


# def basic(inputs,
#           num_classes,
#           is_training=True,
#           dropout_keep_prob=0.8,
#           reuse=tf.compat.v1.AUTO_REUSE):
#
#     with slim.arg_scope(inception_v3.inception_v3_arg_scope()):
#         logits, end_points = inception_v3.inception_v3(inputs,
#                                                        num_classes = num_classes,
#                                                        is_training=is_training,
#                                                        dropout_keep_prob=dropout_keep_prob,
#                                                        reuse=reuse)
#
#     return end_points['Mixed_5d'], logits
