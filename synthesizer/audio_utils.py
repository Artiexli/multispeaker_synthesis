#
# audio_utils.py
#
# Various utilities for manipulating the wav files for preprocessing,
# training, and inference. 

import librosa
import librosa.filters
import numpy as np
import soundfile as sf
from scipy import signal
from scipy.io import wavfile

# Load a wav file given the path + source rate. Note that you really
# want this file to be wav, otherwise librosa will take forever to
# load (especially for formats like m4a).
def load_wav(path, sr):
  return librosa.core.load(path, sr=sr)[0]

# Writes a waveform to file given the npy array, path, and source
# rate. 
def save_wav(wav, path, sr):
  # Proposed by "dsmiller"
  wav *= 32767 / max(0.01, np.max(np.max(np.abs(wav))))
  wavfile.write(path, sr, wav.astype(np.int16))

def save_wavenet_wav(wav, path, sr):
  sf.write(path, wav.astype(np.float32), sr)

def preemphasis(wav, k, preemphasize=True):
  if preemphasize:
    return signal.lfilter([1, -k], [1], wav)
  return wav

def inv_preemphasis(wav, k, inv_preemphasize=True):
  if inv_preemphasize:
    return signal.lfilter([1], [1, -k], wav)
  return wav

# From https://github.com/r9y9/wavenet_vocoder/blob/master/audio.py
def start_and_end_indices(quantized, silence_threshold=2):
  for start in range(quantized.size):
    if abs(quantized[start] - 127) > silence_threshold:
      break
  for end in range(quantized.size - 1, 1, -1):
    if abs(quantized[end] - 127) > silence_threshold:
      break
  
  assert abs(quantized[start] - 127) > silence_threshold
  assert abs(quantized[end] - 127) > silence_threshold
  
  return start, end

def get_hop_size(hparams):
  hop_size = hparams.hop_size
  if hop_size is None:
    assert hparams.frame_shift_ms is not None
    hop_size = int(hparams.frame_shift_ms / 1000 * hparams.sample_rate)
  return hop_size

def linearspectogram(wav, hparams):
  D = _stft(preemphasis(wav, hparams.preemphasis, hparams.preemphasize), hparams)
  S = _amp_to_db(np.abs(D), hparams) - hparams.ref_level_db

  if hparams.signal_normalization:
    return _normalize(S, hparams)
  return S

def melspectogram(wav, hparams):
  D = _stft(preemphasis(wav, hparams.preemphasis, hparams.preemphasize), hparams)
  S = _amp_to_db(_linear_to_mel(np.abs(D), hparams), hparams) - hparams.ref_level_db

  if hparams.signal_normalization:
    return _normalize(S, hparams)
  return S

# Converts linear spectogram to wavefrom using Librosa
def inv_linear_spectogram(linear_spectogram, hparams):
  if hparams.signal_normalization:
    D = _denormalize(linear_spectogram, hparams)
  else:
    D = linear_spectogram
  
  # Convert back into linear
  S = _db_to_amp(D + hparams.ref_level_db) 

  if hparams.use_lws:
    processor = _lws_processor(hparams)
    D = processor.run_lws(S.astype(np.float64).T ** hparams.power)
    y = processor.istft(D).astype(np.float32)
    return inv_preemphasis(y, hparams.preemphasis, hparams.preemphasize)
  else:
    return inv_preemphasis(_griffin_lim(S ** hparams.power, hparams), hparams.preemphasis, hparams.preemphasize)
  
# Converts mel spectogram to waveform using Librosa
def inv_mel_spectogram(mel_spectogram, hparams):
  if hparams.signal_normalization:
    D = _denormalize(mel_spectogram, hparams)
  else:
    D = mel_spectogram
  
  S = _mel_to_linear(_db_to_amp(D + hparams.ref_level_db), hparams)  # Convert back to linear
  
  if hparams.use_lws:
    processor = _lws_processor(hparams)
    D = processor.run_lws(S.astype(np.float64).T ** hparams.power)
    y = processor.istft(D).astype(np.float32)
    return inv_preemphasis(y, hparams.preemphasis, hparams.preemphasize)
  else:
    return inv_preemphasis(_griffin_lim(S ** hparams.power, hparams), hparams.preemphasis, hparams.preemphasize)

def _lws_processor(hparams):
  import lws
  return lws.lws(hparams.n_fft, get_hop_size(hparams), fftsize=hparams.win_size, mode="speech")

# Griffin Lim - a non-ML solution for synthesizing audio from
# waveforms. 
# Based on: Based on https://github.com/librosa/librosa/issues/434
def _griffin_lim(S, hparams):
  angles = np.exp(2j * np.pi * np.random.rand(*S.shape))
  S_complex = np.abs(S).astype(np.complex)
  y = _istft(S_complex * angles, hparams)
  for i in range(hparams.griffin_lim_iters):
    angles = np.exp(1j * np.angle(_stft(y, hparams)))
    y = _istft(S_complex * angles, hparams)
  return y

def _stft(y, hparams):
  if hparams.use_lws:
    return _lws_processor(hparams).stft(y).T
  else:
    return librosa.stft(y=y, n_fft=hparams.n_fft, hop_length=get_hop_size(hparams), win_length=hparams.win_size)
  

def _istft(y, hparams):
  return librosa.istft(y, hop_length=get_hop_size(hparams), win_length=hparams.win_size)

##########################################################
#Those are only correct when using lws!!! (This was messing with Wavenet quality for a long time!)
def num_frames(length, fsize, fshift):
  """Compute number of time frames of spectrogram
  """
  pad = (fsize - fshift)
  if length % fshift == 0:
    M = (length + pad * 2 - fsize) // fshift + 1
  else:
    M = (length + pad * 2 - fsize) // fshift + 2
  return M


def pad_lr(x, fsize, fshift):
  """Compute left and right padding
  """
  M = num_frames(len(x), fsize, fshift)
  pad = (fsize - fshift)
  T = len(x) + 2 * pad
  r = (M - 1) * fshift + fsize - T
  return pad, pad + r
##########################################################
#Librosa correct padding
def librosa_pad_lr(x, fsize, fshift):
  return 0, (x.shape[0] // fshift + 1) * fshift - x.shape[0]

# Conversions
_mel_basis = None
_inv_mel_basis = None

def _linear_to_mel(spectogram, hparams):
  global _mel_basis
  if _mel_basis is None:
    _mel_basis = _build_mel_basis(hparams)
  return np.dot(_mel_basis, spectogram)

def _mel_to_linear(mel_spectrogram, hparams):
  global _inv_mel_basis
  if _inv_mel_basis is None:
    _inv_mel_basis = np.linalg.pinv(_build_mel_basis(hparams))
  return np.maximum(1e-10, np.dot(_inv_mel_basis, mel_spectrogram))

def _build_mel_basis(hparams):
  assert hparams.fmax <= hparams.sample_rate // 2
  return librosa.filters.mel(sr=hparams.sample_rate, n_fft=hparams.n_fft, n_mels=hparams.num_mels,
                             fmin=hparams.fmin, fmax=hparams.fmax)

def _amp_to_db(x, hparams):
  min_level = np.exp(hparams.min_level_db / 20 * np.log(10))
  return 20 * np.log10(np.maximum(min_level, x))

def _db_to_amp(x):
  return np.power(10.0, (x) * 0.05)

def _normalize(S, hparams):
  if hparams.allow_clipping_in_normalization:
    if hparams.symmetric_mels:
      return np.clip((2 * hparams.max_abs_value) * ((S - hparams.min_level_db) / (-hparams.min_level_db)) - hparams.max_abs_value,
                        -hparams.max_abs_value, hparams.max_abs_value)
    else:
      return np.clip(hparams.max_abs_value * ((S - hparams.min_level_db) / (-hparams.min_level_db)), 0, hparams.max_abs_value)
  
  assert S.max() <= 0 and S.min() - hparams.min_level_db >= 0
  if hparams.symmetric_mels:
    return (2 * hparams.max_abs_value) * ((S - hparams.min_level_db) / (-hparams.min_level_db)) - hparams.max_abs_value
  else:
    return hparams.max_abs_value * ((S - hparams.min_level_db) / (-hparams.min_level_db))

def _denormalize(D, hparams):
  if hparams.allow_clipping_in_normalization:
    if hparams.symmetric_mels:
      return (((np.clip(D, -hparams.max_abs_value,
                        hparams.max_abs_value) + hparams.max_abs_value) * -hparams.min_level_db / (2 * hparams.max_abs_value))
              + hparams.min_level_db)
    else:
      return ((np.clip(D, 0, hparams.max_abs_value) * -hparams.min_level_db / hparams.max_abs_value) + hparams.min_level_db)
  
  if hparams.symmetric_mels:
    return (((D + hparams.max_abs_value) * -hparams.min_level_db / (2 * hparams.max_abs_value)) + hparams.min_level_db)
  else:
    return ((D * -hparams.min_level_db / hparams.max_abs_value) + hparams.min_level_db)