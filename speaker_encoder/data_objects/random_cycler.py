#
# random_cycler.py
#
# Creates an internal source of a sequence and allows access to its
# items in a constrained random order. 
#
# For a source sequence of n items and one+ consecutive queries of a
# total of m items, the following are guaranteed (one implies the other)
#   - Each item will be returned between m // n and ((m - 1) // n) + 1 times.
#   - Between two apperances of the same item, there may be at most 2 * (n - 1) other items.

import random

class RandomCycler:
  def __init__(self, source):
    if len(source) == 0:
      raise Exception("RandomCycler was provided an empty collection.")
    self.all_items = list(source)
    self.next_items = []

  def sample(self, count: int):
    shuffle = lambda l: random.sample(l, len(l))

    out = []
    while count > 0:
      if count >= len(self.all_items):
        out.extend(shuffle(list(self.all_items)))
        count -= len(self.all_items)
        continue
      n = min(count, len(self.next_items))
      out.extend(self.next_items[:n])
      count -= n
      self.next_items = self.next_items[n:]
      if len(self.next_items) == 0:
        self.next_items = shuffle(list(self.all_items))
    return out

  def __next__(self):
    return self.sample(1)[0]