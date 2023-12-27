from functools import partial

import torch
from torch.utils.data import ConcatDataset, DataLoader

from src.data.dataloader.data_sampler import EpochBasedSampler
from src.data.dataloader.worker_init import worker_init_fn
from src.data.dataset import SpatioTemporalFusionDataset
from src.data.transforms import *
from src.metrics import *
from src.model.opgan import OPGANGenerator

dataset_cls_func = partial(
    SpatioTemporalFusionDataset,
    data_prefix_tmpl_dict=dict(
        fine_img_01='Landsat_01',
        fine_img_02='Landsat_02',
        coarse_img_01='MODIS_01',
        coarse_img_02='MODIS_02',
    ),
    data_name_tmpl_dict=dict(
        fine_img_01='{}_L_{}',
        fine_img_02='{}_L_{}',
        coarse_img_01='{}_M_{}',
        coarse_img_02='{}_M_{}',
    ),
    is_serialize_data=True,
)

transforms_key_list = [
    'fine_img_01',
    'fine_img_02',
    'coarse_img_01',
    'coarse_img_02',
]

test_transform_list = [
    LoadData(key_list=transforms_key_list),
    RescaleToMinusOneOne(key_list=transforms_key_list, data_range=[0, 10000]),
    Format(key_list=transforms_key_list),
]

test_dataset = dataset_cls_func(
    dataset_name='LGC',
    data_root='data/spatio_temporal_fusion/LGC/private_data/syy_setting-9/test/full',
    transform_func_list=test_transform_list,
)

test_dataloader = DataLoader(
    dataset=test_dataset,
    batch_size=1,
    sampler=EpochBasedSampler(dataset=test_dataset, is_shuffle=False, seed=42),
    num_workers=0,
)

img_channel_num = 6

model = OPGANGenerator(img_channel_num=img_channel_num)

checkpoint_path = (
    'results/opgan/syy_setting-8/RMSProp/checkpoints/model_generator_epoch_349.pth'
)

metric_list = [
    RMSE(is_reduce_channel=False),
    MAE(is_reduce_channel=False),
    PSNR(max_value=1.0),
    SSIM(data_range=1.0, is_reduce_channel=False),
    ERGAS(ratio=1.0 / 16.0),
    CC(is_reduce_channel=False),
    SAM(),
    UIQI(is_reduce_channel=False),
]

# device_info = DeviceInfo(cuda_idx=0, is_auto_empty_cache=True)
# device_info =

__all__ = [
    'test_dataloader',
    'model',
    'checkpoint_path',
    'optimizer',
    'scheduler',
    'metric_list',
]
