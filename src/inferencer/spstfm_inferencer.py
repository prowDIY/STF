import shutil
from pathlib import Path

import numpy as np
import tifffile
import torch
import torch.nn.functional as F
from skimage import io
from torch.utils.tensorboard import SummaryWriter

from src.logger.txt_logger import FusionLogger
from src.utils import EPSILON


class Inferencer:
    def __init__(
        self,
        congfig_path,
        inference_root_dir_path,
        inference_dir_prefix_list=[
            'txt_logs',
            'backend_logs',
            'imgs',
            'configs',
        ],
        #
        txt_logger_name='inference',
        txt_logger_level='INFO',
        #
        test_dataloader=None,
        #
        model=None,
        #
        metric_list=None,
    ):
        self.init_inference_params()
        self.init_inference_dir(
            inference_root_dir_path, inference_dir_prefix_list, congfig_path
        )
        self.init_logger(txt_logger_name, txt_logger_level)
        self.init_dataloader(test_dataloader)
        self.init_model(model)
        self.init_metric(metric_list)

    def init_inference_params(self):
        self.current_epoch = 0
        self.max_epoch = 1000
        self.val_interal = 10

    def init_inference_dir(
        self, inference_root_dir_path, inference_dir_prefix_list, congfig_path
    ):
        self.inference_root_dir_path = Path(inference_root_dir_path)
        self.inference_dir_prefix_list = inference_dir_prefix_list
        self.mkdir()
        shutil.copy(congfig_path, self.inference_configs_dir)

    def mkdir(self):
        for inference_dir_prefix in self.inference_dir_prefix_list:
            inference_dir = self.inference_root_dir_path / inference_dir_prefix
            inference_dir.mkdir(parents=True, exist_ok=True)
            setattr(self, f'inference_{inference_dir_prefix}_dir', inference_dir)

    def init_logger(self, txt_logger_name, txt_logger_level):
        self.txt_logger = FusionLogger(
            logger_name=txt_logger_name,
            log_file=self.inference_txt_logs_dir / 'log.log',
            log_level=txt_logger_level,
        )
        self.backend_logger = SummaryWriter(self.inference_backend_logs_dir)

    def init_dataloader(self, test_dataloader):
        self.test_dataloader = test_dataloader

    def init_model(self, model):
        self.model = model

    def init_metric(self, metric_list):
        self.metric_list = metric_list

    def inference(self):
        for iter_idx, data_per_batch in enumerate(self.test_dataloader):
            (
                reconstruction_input_list,
                show_img_list,
                gt,
                key,
                dataset_name,
                normalize_scale,
                normalize_mode,
            ) = self.before_inference_iter(data_per_batch)
            self.inference_iter(
                iter_idx,
                reconstruction_input_list,
                show_img_list,
                gt,
                key,
                dataset_name,
                normalize_scale,
                normalize_mode,
            )

    def before_inference_iter(self, data_per_batch):
        (
            reconstruction_input_list,
            show_img_list,
        ) = self.get_model_input(data_per_batch)
        gt = self.get_gt(data_per_batch)
        key = data_per_batch['key'][0]
        dataset_name = data_per_batch['dataset_name'][0]
        normalize_scale = data_per_batch['normalize_scale'][0].numpy()
        normalize_mode = data_per_batch['normalize_mode'][0].numpy()
        return (
            reconstruction_input_list,
            show_img_list,
            gt,
            key,
            dataset_name,
            normalize_scale,
            normalize_mode,
        )

    def get_model_input(self, data_per_batch):
        fine_img_01 = data_per_batch['fine_img_01']  # 1, c, h, w
        fine_img_02 = data_per_batch['fine_img_02']
        fine_img_03 = data_per_batch['fine_img_03']
        coarse_img_01 = data_per_batch['coarse_img_01']
        coarse_img_02 = data_per_batch['coarse_img_02']
        coarse_img_03 = data_per_batch['coarse_img_03']

        coarse_diff_dictionary = data_per_batch['coarse_diff_dictionary']
        fine_diff_dictionary = data_per_batch['fine_diff_dictionary']

        reconstruction_input_list = [
            coarse_img_01,
            coarse_img_02,
            coarse_img_03,
            fine_img_01,
            fine_img_03,
            coarse_diff_dictionary,
            fine_diff_dictionary,
        ]

        show_img_list = [
            coarse_img_01,
            coarse_img_02,
            coarse_img_03,
            fine_img_01,
            fine_img_02,
            fine_img_03,
        ]
        return (
            reconstruction_input_list,
            show_img_list,
        )

    def get_gt(self, data_per_batch):
        fine_img_02 = data_per_batch['fine_img_02']
        return fine_img_02

    def inference_iter(
        self,
        iter_idx,
        reconstruction_input_list,
        show_img_list,
        gt,
        key,
        dataset_name,
        normalize_scale,
        normalize_mode,
    ):
        reconstruction_fine_img = self.model.reconstruction(*reconstruction_input_list)
        msg = f'inference iter: {iter_idx}, dataset {dataset_name} '
        for metric in self.metric_list:
            metric_value = metric(reconstruction_fine_img, gt)
            msg += f' {metric.__name__}: {metric_value.item():.4f}'
        self.txt_logger.info(msg)

        ## TODO
        save_dir_prefix = f'{dataset_name}'

        save_dir_path = self.inference_imgs_dir / save_dir_prefix / 'save_img'

        save_name = key.split('-')[-1]
        save_name = save_name[:8] + '_save_img_' + save_name[9:] + '.tif'
        self.img_save(
            reconstruction_fine_img,
            save_dir_path,
            save_name,
            normalize_scale,
            normalize_mode,
        )

        show_dir_prefix = f'{dataset_name}'
        show_dir_path = self.inference_imgs_dir / show_dir_prefix / 'show_img'

        show_name = key.split('-')[-1]
        show_name = show_name[:8] + '_show_img_' + show_name[9:] + '.png'

        self.img_show(
            show_img_list,
            reconstruction_fine_img,
            show_dir_path,
            show_name,
            normalize_mode,
        )

    def inference_iter_per_channel(
        self, HRDI_reconstruction_input_list, img_reconstruction_input_list
    ):
        (
            reconstruction_fine_21_samples,
            reconstruction_fine_32_samples,
        ) = self.model.HRDI_reconstruction(*HRDI_reconstruction_input_list)
        img_reconstruction_input_list = img_reconstruction_input_list + [
            reconstruction_fine_21_samples,
            reconstruction_fine_32_samples,
        ]

        reconstruction_fine_img = self.model.img_reconstruction(
            *img_reconstruction_input_list
        )
        return reconstruction_fine_img

    def img_save(
        self,
        save_tensor,
        save_dir_path,
        save_name,
        normalize_scale,
        normalize_mode,
    ):
        save_img = save_tensor[0].cpu().numpy().transpose(1, 2, 0)
        _, _, c = save_img.shape
        if normalize_mode == 1:
            save_img = save_img * normalize_scale
        elif normalize_mode == 2:
            save_img = (save_img + 1.0) / 2.0 * normalize_scale
        save_img = np.clip(save_img, 0, normalize_scale)
        if normalize_scale == 255:
            save_img = save_img.astype(np.uint8)
        else:
            save_img = save_img.astype(np.uint16)
        save_img_path = save_dir_path / save_name
        save_dir_path.mkdir(parents=True, exist_ok=True)
        tifffile.imsave(save_img_path, save_img)

    def img_show(
        self,
        show_img_list,
        pred_tensor,
        show_dir_path,
        show_name,
        normalize_mode,
        img_interval=10,
    ):
        show_len = len(show_img_list)
        h_num, w_num = 3, show_len // 2
        _, c, h, w = pred_tensor.shape
        show_img = np.zeros(
            (
                (h + img_interval) * h_num + img_interval,
                (w + img_interval) * w_num + img_interval,
                3,
            ),
            dtype=np.uint8,
        )
        for h_index in range(h_num - 1):
            for w_index in range(w_num):
                show_sub_img = (
                    show_img_list[h_index * w_num + w_index][0]
                    .cpu()
                    .numpy()
                    .transpose(1, 2, 0)
                )
                if normalize_mode == 1:
                    show_sub_img = show_sub_img * 255.0
                elif normalize_mode == 2:
                    show_sub_img = (show_sub_img + 1.0) / 2.0 * 255.0
                if c == 6:
                    show_sub_img = show_sub_img[:, :, (3, 2, 1)]
                show_sub_img = np.clip(show_sub_img, 0, 255).astype(np.uint8)
                show_img[
                    img_interval * (h_index + 1)
                    + h_index * h : img_interval * (h_index + 1)
                    + (h_index + 1) * h,
                    img_interval * (w_index + 1)
                    + w_index * w : img_interval * (w_index + 1)
                    + (w_index + 1) * w,
                    :,
                ] = show_sub_img

        show_sub_img = pred_tensor[0].cpu().numpy().transpose(1, 2, 0)
        if normalize_mode == 1:
            show_sub_img = show_sub_img * 255.0
        elif normalize_mode == 2:
            show_sub_img = (show_sub_img + 1.0) / 2.0 * 255.0
        if c == 6:
            show_sub_img = show_sub_img[:, :, (3, 2, 1)]
        show_sub_img = np.clip(show_sub_img, 0, 255).astype(np.uint8)
        show_img[
            img_interval * h_num + h * (h_num - 1) : img_interval * h_num + h * h_num,
            img_interval : img_interval + w,
            :,
        ] = show_sub_img

        show_img_path = show_dir_path / show_name
        show_dir_path.mkdir(parents=True, exist_ok=True)

        io.imsave(show_img_path, show_img)
