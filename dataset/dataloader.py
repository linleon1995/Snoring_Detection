
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# from cfg import DATA_PATH
from typing import AbstractSet
import torch
import torchaudio
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms, datasets
import numpy as np
import os
import cv2
import matplotlib.pyplot as plt
from dataset import preprocess_utils
from dataset import input_preprocess
from dataset import dataset_utils
from dataset import transformations
from utils import configuration


def minmax_normalization(image):
    img_max = np.max(image)
    img_min = np.min(image)
    return (image-img_min) / (img_max-img_min)


def convert_value(image, value_pair=None):
    # TODO: one-to-one mapping, non-repeat
    # TODO: label pair convert
    for k in value_pair:
        image[image==k] = value_pair[k]
    return image


def create_kaggle_snoring_dataloader():
    load_func = None
    gen_index_func = dataset_utils.generate_kaggle_snoring_index

    kaggle_snoring_dataloader = KaggleSnoringDataset(load_func,
                                                     gen_index_func,)
    return kaggle_snoring_dataloader
    

# TODO: check data shape and type
# TODO: check whether python abc helpful?
class AbstractDastaset(Dataset):
    def __init__(self, config, mode):
        assert (mode=='train' or mode=='valid'), f'Unknown executing mode [{mode}].'
        self.dataset_config = config.dataset.train if mode == 'train' else config.dataset.val
        self.model_config = config.model
        self.preprocess_config = self.dataset_config.preprocess_config
        self.is_data_augmentation = self.dataset_config.is_data_augmentation
        self.mode = mode
        self.transform = transforms.Compose([transforms.ToTensor()])
        # self.load_func = load_func

        self.check_dataset_split(config.dataset.data_split)
        # TODO: General solution
        self.input_data_indices, self.ground_truth_indices = [], []
        # self.input_data_indices, self.ground_truth_indices = dataset_utils.get_data_indices(
        #     data_name=config.dataset.data_name,
        #     data_path=config.dataset.data_path,
        #     save_path=config.dataset.index_path,
        #     mode=self.mode,
        #     data_split=config.dataset.data_split,
        #     generate_index_func=self.generate_index_func)

        # TODO: logger
        print(f"{self.mode}  Samples: {len(self.input_data_indices)}")

    def __len__(self):
        return len(self.input_data_indices)

    def __getitem__(self, idx):
        input_data = self.data_loading_function(self.input_data_indices[idx])
        input_data = self.preprocess(input_data)
        input_data = self.transform(input_data)
        if self.ground_truth_indices is not None:
            ground_truth = self.data_loading_function(self.ground_truth_indices[idx])
            ground_truth = self.preprocess(ground_truth)
            ground_truth = self.transform(ground_truth)
        else:
            ground_truth = None
        return {'input': input_data, 'gt': ground_truth}

    def data_loading_function(self, fielname):
        return fielname

    def preprocess(self, data):
        return data

    def check_dataset_split(self, data_split):
        assert (isinstance(data_split, list) or isinstance(data_split, tuple))
        assert data_split[0] + data_split[1] == 1

    # def generate_index_func(self):
    #     return dataset_utils.generate_kaggle_breast_ultrasound_index

class AudioDataset(AbstractDastaset):
    def __init__(self, config, mode):
        super().__init__(config, mode)
        # self.preprocess_method = config.dataset_config.preprocess_config
        self.input_data_indices = dataset_utils.load_content_from_txt(
                os.path.join(config.dataset.index_path, f'{mode}.txt'))
        self.ground_truth_indices = [int(os.path.split(os.path.split(f)[0])[1]) for f in self.input_data_indices]
        # self.ground_truth_indices = [int(os.path.basename(f)[0]) for f in self.input_data_indices]
        self.transform_methods = config.dataset.transform_methods
        print(f"{self.mode}  Samples: {len(self.input_data_indices)}")

    def data_loading_function(self, filename):
        return torchaudio.load(filename)

    def preprocess(self, data):
        features = self.audio_trasform(data)
        if len(features) > 1:
            audio_feature = self.merge_audio_features(features)
        else:
            audio_feature = list(features.values())[0]
        return audio_feature

    def audio_trasform(self, data):
        # TODO: different method, e.g., mel-spectogram, MFCC, time-domain
        waveform, sample_rate = data
        # TODO: how to use time-domain data, split to clips?
        # if len(self.transform_methods) == 0:
        #     return waveform
        features = {}
        for method in self.transform_methods:
            if method == 'fbank':
                features[method] = transformations.fbank(waveform, sample_rate)
            elif method == 'spectrogram':
                features[method] = transformations.spectrogram(waveform, sample_rate)
            elif method == 'mel-spectrogram':
                features[method] = transformations.mel_spec(waveform, sample_rate)
            elif method == 'MFCC':
                features[method] = transformations.MFCC(waveform, sample_rate)
            else:
                raise ValueError('Unknown audio transformations')
        return features

    def __getitem__(self, idx):
        input_data = self.data_loading_function(self.input_data_indices[idx])
        input_data = self.preprocess(input_data)
        # input_data = self.transform(input_data)
        if self.ground_truth_indices is not None:
            ground_truth = self.ground_truth_indices[idx]
        else:
            ground_truth = None
        # TODO: general solution for channel issue
        input_data = torch.unsqueeze(input_data, 0)
        input_data = input_data.repeat(3, 1, 1)
        return {'input': input_data, 'gt': ground_truth}

    def merge_audio_features(self):
        pass


class KaggleSnoringDataset(AudioDataset):
    def __init__(self, config, mode):
        super().__init__(config, mode)

    def preprocess(self, data):
        # data = self.audio_preprocess(data)
        return data


if __name__ == "__main__":
    pass
        