#
# synthesizer_dataset.py
#
# Dataset object for loading preprocessed synthesizer data.

import torch
from torch.utils.data import Dataset
import numpy as np
from pathlib import Path
from synthesizer.utils.text import text_to_sequence

# Custom dataset for loading our data on the fly.
class SynthesizerDataset(Dataset):
  def __init__(self, metadata_fpath: Path, mel_dir: Path, embed_dir: Path, hparams):
    print("[INFO] SynthesizerDataset - Using inputs from:\n\t%s\n\t%s\n\t%s" % (metadata_fpath, mel_dir, embed_dir))

    # Open the dataset metadata file that we created during 
    # preprocessing.
    with metadata_fpath.open("r") as metadata_file:
      metadata = [line.split("|") for line in metadata_file]
    
    mel_fnames = [x[1] for x in metadata if int(x[4])]
    mel_fpaths = [mel_dir.joinpath(fname) for fname in mel_fnames]
    embed_fnames = [x[2] for x in metadata if int(x[4])]
    embed_fpaths = [embed_dir.joinpath(fname) for fname in embed_fnames]
    self.samples_fpaths = list(zip(mel_fpaths, embed_fpaths))
    self.samples_texts = [x[5].strip() for x in metadata if int(x[4])]
    self.metadata = metadata
    self.hparams = hparams
  
    print("[INFO] SynthesizerDataset - Located %d samples." % len(self.samples_fpaths))

  def __len__(self):
    return len(self.samples_fpaths)

  # Load samples and preprocess them accordingly. Returns the text,
  # mel spectogram solution, embedding, and the given index.
  def __getitem__(self, index):
    # Note sometimes the index may be a list of two? In that case, just
    # return a single item corresponding to the first element.
    if index is list:
      index = index[0]
    
    mel_path, embed_path = self.samples_fpaths[index]
    mel = np.load(mel_path).T.astype(np.float32)

    # Load the embedding.
    embed = np.load(embed_path)

    # Preprocess the text. 
    text = text_to_sequence(self.samples_texts[index], self.hparams.tts_cleaner_names)

    # COnvert the list returned by text_to_sequence to a numpy arary
    text = np.asarray(text).astype(np.int32)

    return text, mel.astype(np.float32), embed.astype(np.float32), index


# Custom collate method to group speakers together in a batch. 
def collate_synthesizer(batch, r, hparams):
  # Text.
  x_lens = [len(x[0]) for x in batch]
  max_x_len = max(x_lens)

  chars = [pad1d(x[0], max_x_len) for x in batch]
  chars = np.stack(chars)

  # Mel spectogram.
  spec_lens = [x[1].shape[-1] for x in batch]
  max_spec_len = max(spec_lens) + 1
  if max_spec_len % r != 0:
    max_spec_len += r - max_spec_len % r

  # WaveRNN mel spectograms are normalized to [0, 1] so that zero padding
  # adds silence. By default, SV2TTS uses symmetric mels, where
  # -1 * max_abs_value is the silence. 
  if hparams.symmetric_mels:
    mel_pad_value = -1 * hparams.max_abs_value
  else:
    mel_pad_value = 0
  
  mel = [pad2d(x[1], max_spec_len, pad_value = mel_pad_value) for x in batch]
  mel = np.stack(mel)

  # Speaker embedding with the speaker encoder. 
  embeds = np.array([x[2] for x in batch])

  # Index (for vocoder preprocessing)
  indices = [x[3] for x in batch]

  # Convert everyting to tensors
  chars = torch.tensor(chars).long()
  mel = torch.tensor(mel)
  embeds = torch.tensor(embeds)

  return chars, mel, embeds, indices

def pad1d(x, max_len, pad_value=0):
  return np.pad(x, (0, max_len - len(x)), mode="constant", constant_values=pad_value)

def pad2d(x, max_len, pad_value=0):
  return np.pad(x, ((0, 0), (0, max_len - x.shape[-1])), mode="constant", constant_values=pad_value)