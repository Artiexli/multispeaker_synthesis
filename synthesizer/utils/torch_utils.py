#
# torch_utils.py
#
# Assorted data methods + classes for training. 

import torch

_output_ref = None
_replicas_ref = None

# For executing training on multiple graphics cards.
def data_parallel_workaround(model, *input):
  global _output_ref
  global _replicas_ref

  device_ids = list(range(torch.cuda.device_count()))
  # Output device is always the first graphics card.
  output_device = device_ids[0]
  replicas = torch.nn.parallel.replicate(model, device_ids)
  inputs = torch.nn.parallel.scatter(input, device_ids)
  replicas = replicas[:len(inputs)]
  outputs = torch.nn.parallel.parallel_apply(replicas, inputs)
  y_hat = torch.nn.parallel.gather(outputs, output_device)
  _output_ref = outputs
  _replicas_ref = replicas
  return y_hat

class ValueWindow():
  def __init__(self, window_size=100):
    self._window_size = window_size
    self._values = []

  def append(self, x):
    self._values = self._values[-(self._window_size - 1):] + [x]

  @property
  def sum(self):
    return sum(self._values)

  @property
  def count(self):
    return len(self._values)

  @property
  def average(self):
    return self.sum / max(1, self.count)

  def reset(self):
    self._values = []