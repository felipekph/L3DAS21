import argparse
import os
import numpy as np
import librosa
import pickle
'''
Take as input the unzipped dataset folders and output pickle lists
containing the pre-processed data for task1 and task2, separately.
Separate training, validation and test matrices are saved.
Command line inputs define which task to process and its parameters.
'''


def preprocessing_task1(args):
    sr_task1 = 16000
    def pad(x, size=sr_task1*10):
        #pad all sounds to 10 seconds
        length = x.shape[-1]
        if length > size:
            pad = x[:,:size]
        else:
            pad = np.zeros((x.shape[0], size))
            pad[:,:length] = x
        return pad

    train100_folder = 'train'
    train360_folder = 'train360'
    dev_folder = 'test'

    sets = [train100_folder, dev_folder]
    predictors_train = []
    predictors_test = []
    target_train = []
    target_test = []
    for folder in sets:
        train_count = 0
        dev_count = 0
        print ('Processing ' + folder + ' folder...')
        main_folder = os.path.join(args.input_path, folder)
        contents = os.listdir(main_folder)
        for sub in contents:
            sub_folder = os.path.join(main_folder, sub)
            contents_sub = os.listdir(sub_folder)
            for lower in contents_sub:
                lower_folder = os.path.join(sub_folder, lower)
                data_path = os.path.join(lower_folder, 'data')
                data = os.listdir(data_path)
                data = [i for i in data if i.split('.')[0].split('_')[-1]=='A']  #filter files with mic B
                for sound in data:
                    sound_path = os.path.join(data_path, sound)
                    target_path = sound_path.replace('data', 'labels').replace('_A', '')
                    samples, sr = librosa.load(sound_path, sr_task1, mono=False)
                    samples = pad(samples)
                    if args.num_mics == 2:  # if both ambisonics mics are wanted
                        #stack the additional 4 channels to get a (8, samples) shape
                        B_sound_path = sound_path.replace('A', 'B')
                        samples_B, sr = librosa.load(sound_path, sr_task1, mono=False)
                        samples_B = pad(samples_B)
                        samples = np.vstack((samples,samples_B))
                    samples_target, sr = librosa.load(target_path, sr_task1, mono=False)
                    samples_target = samples_target.reshape((1, samples_target.shape[0]))
                    samples_target = pad(samples_target)
                    #append to final arrays
                    if folder == dev_folder:
                        predictors_test.append(samples)
                        target_test.append(samples_target)
                        dev_count += 1

                    else:
                        predictors_train.append(samples)
                        target_train.append(samples_target)
                        train_count += 1

                    if args.num_data is not None:
                        if train_count >= args.num_data:
                            if dev_count train_ >= args.num_data:
                        break

    #split train set into train and development
    split_point = int(len(predictors_train) * args.train_val_split)

    predictors_training = predictors_train[:split_point]    #attention: changed training names
    target_training = target_train[:split_point]
    predictors_validation = predictors_train[split_point:]
    target_validation = target_train[split_point:]

    print ('Saving files')
    if not os.path.isdir(args.output_path):
        os.makedirs(args.output_path)

    with open(os.path.join(args.output_path,'task1_predictors_train.pkl'), 'wb') as f:
        pickle.dump(predictors_training, f)
    with open(os.path.join(args.output_path,'task1_predictors_validation.pkl'), 'wb') as f:
        pickle.dump(predictors_validation, f)
    with open(os.path.join(args.output_path,'task1_predictors_test.pkl'), 'wb') as f:
        pickle.dump(predictors_test, f)
    with open(os.path.join(args.output_path,'task1_target_train.pkl'), 'wb') as f:
        pickle.dump(target_training, f)
    with open(os.path.join(args.output_path,'task1_target_validation.pkl'), 'wb') as f:
        pickle.dump(target_validation, f)
    with open(os.path.join(args.output_path,'task1_target_test.pkl'), 'wb') as f:
        pickle.dump(target_test, f)


def preprocessing_task2(args):
    sr_task2 = 32000



if __name__ == '__main__':


    parser = argparse.ArgumentParser()
    #i/o
    parser.add_argument('--task_number', type=int,
                        help='task to be pre-processed')
    parser.add_argument('--input_path', type=str, default='DATASET/Task1',
                        help='directory where the dataset has been downloaded')
    parser.add_argument('--output_path', type=str, default='DATASET/processed',
                        help='where to save the numpy matrices')

    #processing type
    parser.add_argument('--processsing_type', type=str, default='stft',
                        help='stft or waveform')

    parser.add_argument('--train_val_split', type=float, default=0.7,
                        help='perc split between train and validation sets')
    parser.add_argument('--num_mics', type=int, default=1,
                        help='how many ambisonics mics (1 or 2)')
    parser.add_argument('--num_data', type=float, default=None,
                        help='how many datapoints per set. 0 means all available data')
    parser.add_argument('--stft_nparseg', type=int, default=256,
                        help='num of stft frames')
    parser.add_argument('--stft_noverlap', type=int, default=128,
                        help='num of overlapping samples for stft')
    parser.add_argument('--stft_window', type=str, default='hamming',
                        help='stft window_type')

    args = parser.parse_args()

    if args.task_number == 1:
        preprocessing_task1(args)
    elif args.task_number == 2:
        preprocessing_task2(args)