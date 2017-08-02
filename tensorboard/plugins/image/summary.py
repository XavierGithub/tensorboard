# Copyright 2017 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Image summaries and TensorFlow operations to create them.

An image summary stores the width, height, and PNG-encoded data for zero
or more images in a rank-1 string array: `[w, h, png0, png1, ...]`.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import threading

import numpy as np
import tensorflow as tf

from tensorboard.plugins.image import metadata


def op(name,
       images,
       max_outputs=3,
       display_name=None,
       description=None,
       collections=None):
  """Create an image summary op for use in a TensorFlow graph.

  Arguments:
    name: A unique name for the generated summary node.
    images: A `Tensor` representing pixel data with shape `[k, w, h, c]`,
      where `k` is the number of images, `w` and `h` are the width and
      height of the images, and `c` is the number of channels, which
      should be 1, 3, or 4. Any of the dimensions may be statically
      unknown (i.e., `None`).
    max_outputs: Optional `int` or rank-0 integer `Tensor`. At most this
      many images will be emitted at each step. When more than
      `max_outputs` many images are provided, the first `max_outputs` many
      images will be used and the rest silently discarded.
    display_name: Optional name for this summary in TensorBoard, as a
      constant `str`. Defaults to `name`.
    description: Optional long-form description for this summary, as a
      constant `str`. Markdown is supported. Defaults to empty.
    collections: Optional list of graph collections keys. The new
      summary op is added to these collections. Defaults to
      `[Graph Keys.SUMMARIES]`.

  Returns:
    A TensorFlow summary op.
  """
  if display_name is None:
    display_name = name
  summary_metadata = metadata.create_summary_metadata(
      display_name=display_name, description=description)
  with tf.name_scope(name), \
       tf.control_dependencies([tf.assert_rank(images, 4),
                                tf.assert_type(images, tf.uint8),
                                tf.assert_non_negative(max_outputs)]):
    limited_images = images[:max_outputs]
    encoded_images = tf.map_fn(tf.image.encode_png, limited_images,
                               dtype=tf.string,
                               name='encode_each_image')
    image_shape = tf.shape(images)
    dimensions = tf.stack([tf.as_string(image_shape[1], name='width'),
                           tf.as_string(image_shape[2], name='height')],
                          name='dimensions')
    tensor = tf.concat([dimensions, encoded_images], axis=0)
    return tf.summary.tensor_summary(name='image_summary',
                                     tensor=tensor,
                                     collections=collections,
                                     summary_metadata=summary_metadata)


def pb(name, images, max_outputs=3, display_name=None, description=None):
  """Create an image summary protobuf.

  This behaves as if you were to create an `op` with the same arguments
  (wrapped with constant tensors where appropriate) and then execute
  that summary op in a TensorFlow session.

  Arguments:
    name: A unique name for the generated summary, including any desired
      name scopes.
    images: An `np.array` representing pixel data with shape
      `[k, w, h, c]`, where `k` is the number of images, `w` and `h` are
      the width and height of the images, and `c` is the number of
      channels, which should be 1, 3, or 4.
    max_outputs: Optional `int`. At most this many images will be
      emitted. If more than this many images are provided, the first
      `max_outputs` many images will be used and the rest silently
      discarded.
    display_name: Optional name for this summary in TensorBoard, as a
      `str`. Defaults to `name`.
    description: Optional long-form description for this summary, as a
      `str`. Markdown is supported. Defaults to empty.

  Returns:
    A `tf.Summary` protobuf object.
  """
  images = np.array(images).astype(np.uint8)
  if images.ndim != 4:
    raise ValueError('Shape %r must have rank 4' % (images.shape, ))

  limited_images = images[:max_outputs]
  encoded_images = [_encode_png(image) for image in limited_images]
  (width, height) = (images.shape[1], images.shape[2])
  content = [str(width), str(height)] + encoded_images
  tensor = tf.make_tensor_proto(content, dtype=tf.string)

  if display_name is None:
    display_name = name
  summary_metadata = metadata.create_summary_metadata(
      display_name=display_name, description=description)

  summary = tf.Summary()
  summary.value.add(tag='%s/image_summary' % name,
                    metadata=summary_metadata,
                    tensor=tensor)
  return summary


class _TensorFlowPNGEncoder(object):

  def __init__(self):
    super(_TensorFlowPNGEncoder, self).__init__()
    self._session = None
    self._image_placeholder = None
    self._encode_op = None
    self._initialization_lock = threading.Lock()

  def _lazily_initialize(self):
    with self._initialization_lock:
      if self._session:
        return
      graph = tf.Graph()
      with graph.as_default():
        self._image_placeholder = tf.placeholder(
            dtype=tf.uint8, name='image_to_encode')
        self._encode_op = tf.image.encode_png(self._image_placeholder)
      self._session = tf.Session(graph=graph)

  def encode(self, image):
    self._lazily_initialize()
    return self._session.run(self._encode_op,
                             feed_dict={self._image_placeholder: image})


_encoder = _TensorFlowPNGEncoder()


def _encode_png(image):
  # We use a TensorFlow backend to encode images from Python.
  return _encoder.encode(image)
