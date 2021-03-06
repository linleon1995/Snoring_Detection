# Classification task on Breast Ultrasound
import os
import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from dataset.dataloader import AudioDataset
from models.image_classification import img_classifier
from utils import train_utils
from dataset import dataset_utils
from utils import configuration
from utils import metrics
from pprint import pprint
from torch.cuda.amp import autocast, GradScaler
ImageClassifier = img_classifier.ImageClassifier
from tensorboardX import SummaryWriter
import random
# device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
# # device = torch.device('cpu')
# print('Using device: {}'.format(device))
CONFIG_PATH = rf'C:\Users\test\Desktop\Leon\Projects\Snoring_Detection\config\_cnn_train_config.yml'

logger = train_utils.get_logger('train')





def main(config_reference):
    # Load and log experiment configuration
    config = configuration.load_config(config_reference)
    device = config.device
    pprint(config)

    manual_seed = config.get('manual_seed', None)
    if manual_seed is not None:
        logger.info(f'Seed the RNG for all devices with {manual_seed}')
        torch.manual_seed(manual_seed)
        # see https://pytorch.org/docs/stable/notes/randomness.html
        torch.cuda.manual_seed(manual_seed)
        torch.cuda.manual_seed_all(manual_seed)
        np.random.seed(manual_seed)
        random.seed(manual_seed)
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True

    all_checkpoint_path = os.path.join(config.train.project_path, 'checkpoints')
    checkpoint_path = train_utils.create_training_path(all_checkpoint_path)
    config['checkpoint_path'] = checkpoint_path
    # TODO: selective pretrained
    # TODO: dynamic output structure
    net = ImageClassifier(
        backbone=config.model.name, in_channels=config.model.in_channels, activation=config.model.activation,
        out_channels=config.model.out_channels, pretrained=config.model.pretrained, dim=1, output_structure=None)
    if torch.cuda.is_available():
        net.cuda()
    optimizer = train_utils.create_optimizer(config.optimizer_config, net)

    
    # Dataloader
    train_dataset = AudioDataset(config, mode='train')
    train_dataloader = DataLoader(
        train_dataset, batch_size=config.dataset.batch_size, shuffle=config.dataset.shuffle, pin_memory=config.train.pin_memory, num_workers=config.train.num_workers)
    # TODO: config.dataset.preprocess_config.mix_up = None
    # config.dataset.preprocess_config.mix_up = None
    test_dataset = AudioDataset(config, mode='valid')
    test_dataloader = DataLoader(
        test_dataset, batch_size=1, shuffle=False, pin_memory=config.train.pin_memory, num_workers=config.train.num_workers)

    # Start training
    training_samples = len(train_dataloader.dataset)
    training_steps = max(training_samples//config.dataset.batch_size, 1)
    testing_samples = len(test_dataloader.dataset)
    show_times = 5
    displaying_step = max(training_steps//show_times//show_times*show_times, 1)
    

    # Logger
    # TODO: train_logging
    logger.info("Start Training!!")
    logger.info("Training epoch: {} Batch size: {} Shuffling Data: {} Training Samples: {}".
            format(config.train.epoch, config.dataset.batch_size, config.dataset.shuffle, training_samples))
    
    train_utils.config_logging(os.path.join(checkpoint_path, 'logging.txt'), config, access_mode='w+')
    # experiment = os.path.basename(checkpoint_path)
    # config['experiment'] = experiment
    # all_checkpoint_path = os.path.join(config.train.project_path, 'checkpoints')
    # if not os.path.isdir(all_checkpoint_path):
    #     os.mkdir(all_checkpoint_path)
    # train_utils.train_logging(os.path.join(all_checkpoint_path, 'train_logging.txt'), config)


    print(60*"-")
    loss_func = train_utils.get_loss(config.train.loss)
    train_writer = SummaryWriter(log_dir=os.path.join(checkpoint_path, 'train'))
    test_writer = SummaryWriter(log_dir=os.path.join(checkpoint_path, 'valid'))
    max_acc = -1
    n_iter, test_n_iter = 0, 0
    scaler = GradScaler()
    for epoch in range(1, config.train.epoch+1):
        total_train_loss, total_test_loss = 0.0, 0.0
        print(60*"=")
        logger.info(f'Epoch {epoch}/{config.train.epoch}')
        net.train()
        for i, data in enumerate(train_dataloader, 1):
            n_iter += 1
            
            inputs, labels = data['input'], data['gt']
            inputs = train_utils.minmax_norm(inputs)

            # img = inputs[0,0]
            # # plot_specgram(img, sample_rate)
            # def show_fig():
            #     # min_val = 10 * np.log10(inputs.min())
            #     # max_val = 10 * np.log10(inputs.max())
            #     import cv2
            #     # inputs = train_utils.minmax_norm(inputs)
            #     img = inputs.numpy()[0,0]
            #     # img = np.uint8(img*255)
            #     # img = np.uint8(cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX))
            #     # vv = 0.1
            #     # uu = 0.5
            #     # img[img<vv] = uu
            #     # img = cv2.equalizeHist(img)   
            #     # plt.hist(img)

            #     # if i > 40:
            #     import librosa
            #     # librosa.display.specshow(img, sr=16000, fmin=1, fmax=8000, hop_length=1024)
            #     fig, ax = plt.subplots(1,1)
            #     img = librosa.power_to_db(img, ref=np.max)
            #     imgshow = librosa.display.specshow(img, y_axis='log', sr=22050, hop_length=512,
            #                             x_axis='time', ax=ax)
            #     # plt.imshow(img)
            #     ax.set(title='Log-frequency power spectrogram')
            #     ax.label_outer()
            #     fig.colorbar(imgshow, ax=ax, format="%+2.f dB")
                
            #     plt.show()



            inputs, labels = inputs.to(device), labels.to(device)
            
            # # optimization if amp is not used
            # outputs = net(inputs)
            # loss = loss_func(outputs, labels.float())
            # optimizer.zero_grad()
            # loss.backward()
            # optimizer.step()
            
            # optimiztion if amp is used
            with autocast():
                outputs = net(inputs)
                # loss = loss_func(outputs, labels.float())
                # loss = loss_func(outputs, labels.long())
                # loss = loss_func(outputs, torch.argmax(labels, dim=1))
                if isinstance(loss_func, torch.nn.CrossEntropyLoss):
                    loss = loss_func(outputs, torch.argmax(labels.long(), axis=1))
                else:
                    loss = loss_func(outputs, labels)
            optimizer.zero_grad()
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()


            loss = loss.item()
            train_writer.add_scalar('Loss/step', loss, n_iter)
            total_train_loss += loss
            
            if i%displaying_step == 0:
                logger.info('Step {}  Step loss {}'.format(i, loss))

        train_writer.add_scalar('Loss/epoch', total_train_loss/training_steps, epoch)
        
        with torch.no_grad():
            net.eval()
            eval_tool = metrics.SegmentationMetrics(config.model.out_channels, ['accuracy'])
            for _, data in enumerate(test_dataloader):
                test_n_iter += 1
                inputs, labels = data['input'], data['gt']
                inputs = train_utils.minmax_norm(inputs)
                inputs, labels = inputs.to(device), labels.to(device)
                outputs = net(inputs)
                # loss = loss_func(outputs, labels.float()).item()
                # loss = loss_func(outputs, labels.long()).item()
                if isinstance(loss_func, torch.nn.CrossEntropyLoss):
                    loss = loss_func(outputs, torch.argmax(labels.long(), axis=1))
                else:
                    loss = loss_func(outputs, labels)
                # loss = loss_func(outputs, torch.argmax(labels, dim=1)).item()
                total_test_loss += loss.item()
                # test_writer.add_scalar('Loss/step', loss, test_n_iter)

                # TODO: torch.nn.functional.sigmoid(outputs)
                # prob = torch.nn.functional.softmax(outputs, dim=1)
                prob = torch.sigmoid(outputs)
                prediction = torch.argmax(prob, dim=1)
                labels = torch.argmax(labels, dim=1)
                labels = labels.cpu().detach().numpy()
                prediction = prediction.cpu().detach().numpy()
                evals = eval_tool(labels, prediction)
            # avg_test_acc = evals['accuracy'].item()
            avg_test_acc = metrics.accuracy(
                np.sum(eval_tool.total_tp), np.sum(eval_tool.total_fp), np.sum(eval_tool.total_fn), np.sum(eval_tool.total_tn)).item()
            
            test_writer.add_scalar('Accuracy/epoch', avg_test_acc, epoch)
            test_writer.add_scalar('Loss/epoch', total_test_loss/testing_samples, epoch)

            checkpoint = {
                "net": net.state_dict(),
                'optimizer':optimizer.state_dict(),
                "epoch": epoch
                }
                
            if avg_test_acc > max_acc:
                max_acc = avg_test_acc
                logger.info(f"-- Saving best model with testing accuracy {max_acc:.3f} --")
                checkpoint_name = 'ckpt_best.pth'
                torch.save(checkpoint, os.path.join(checkpoint_path, checkpoint_name))

            if epoch%config.train.checkpoint_saving_steps == 0:
                logger.info(f"Saving model with testing accuracy {avg_test_acc:.3f} in epoch {epoch} ")
                checkpoint_name = 'ckpt_best_{:04d}.pth'.format(epoch)
                torch.save(checkpoint, os.path.join(checkpoint_path, checkpoint_name))

    train_writer.close()
    test_writer.close()

if __name__ == '__main__':
    main(CONFIG_PATH)
    pass
