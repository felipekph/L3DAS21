import os, sys
import numpy as np
import pickle
import math
import pandas as pd
import torch
from scipy.signal import stft
import librosa

'''
Miscellaneous utilities
'''

def save_model(model, optimizer, state, path):
    if isinstance(model, torch.nn.DataParallel):
        model = model.module  # save state dict of wrapped module
    if len(os.path.dirname(path)) > 0 and not os.path.exists(os.path.dirname(path)):
        os.makedirs(os.path.dirname(path))
    torch.save({
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'state': state,  # state of training loop (was 'step')
    }, path)


def load_model(model, optimizer, path, cuda):
    if isinstance(model, torch.nn.DataParallel):
        model = model.module  # load state dict of wrapped module
    if cuda:
        checkpoint = torch.load(path)
    else:
        checkpoint = torch.load(path, map_location='cpu')
    try:
        model.load_state_dict(checkpoint['model_state_dict'])
    except:
        # work-around for loading checkpoints where DataParallel was saved instead of inner module
        from collections import OrderedDict
        model_state_dict_fixed = OrderedDict()
        prefix = 'module.'
        for k, v in checkpoint['model_state_dict'].items():
            if k.startswith(prefix):
                k = k[len(prefix):]
            model_state_dict_fixed[k] = v
        model.load_state_dict(model_state_dict_fixed)
    if optimizer is not None:
        optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
    if 'state' in checkpoint:
        state = checkpoint['state']
    else:
        # older checkpoints only store step, rest of state won't be there
        state = {'step': checkpoint['step']}
    return state


def spectrum_fast(x, nperseg=512, noverlap=128, window='hamming', cut_dc=True,
                  output_phase=True, cut_last_timeframe=True):
    '''
    Compute magnitude spectra from monophonic signal
    '''

    f, t, seg_stft = stft(x,
                        window=window,
                        nperseg=nperseg,
                        noverlap=noverlap)

    #seg_stft = librosa.stft(x, n_fft=nparseg, hop_length=noverlap)

    output = np.abs(seg_stft)

    if output_phase:
        phase = np.angle(seg_stft)
        output = np.concatenate((output,phase), axis=-3)

    if cut_dc:
        output = output[:,1:,:]

    if cut_last_timeframe:
        output = output[:,:,:-1]

    #return np.rot90(np.abs(seg_stft))
    return output

def gen_submission_list_task2(sed, doa, max_loc_value=2.,num_frames=600, num_classes=14, max_overlaps=3):
    '''
    Process sed and doa output matrices (model's output) and generate a list of active sounds
    and their location for every frame. The list has the correct format for the Challenge results
    submission.
    '''
    output = []
    for i, (c, l) in enumerate(zip(sed, doa)):  #iterate all time frames
        c = np.round(c)  #turn to 0/1 the class predictions with threshold 0.5
        l = l * max_loc_value  #turn back locations between -2,2 as in the original dataset
        l = l.reshape(num_classes, max_overlaps, 3)  #num_class, event number, coordinates
        if np.sum(c) == 0:  #if no sounds are detected in a frame
            pass            #don't append
        else:
            for j, e in enumerate(c):  #iterate all events
                if e != 0:  #if an avent is predicted
                    #append list to output: [time_frame, sound_class, x, y, z]
                    predicted_class = int(j/max_overlaps)
                    num_event = int(j%max_overlaps)
                    curr_list = [i, predicted_class, l[predicted_class][num_event][0], l[predicted_class][num_event][1], l[predicted_class][num_event][2]]
                    output.append(curr_list)

    return np.array(output)


def csv_to_matrix_task2(path, class_dict, dur=60, step=0.1, max_overlap=3,
                        max_loc_value=2.):
    '''
    Read label csv file fro task 2 and
    Output a matrix containing 100msecs frames, each filled with
    the class ids of all sounds present and their location coordinates.
    '''
    tot_steps =int(dur/step)
    num_classes = len(class_dict)
    num_frames = int(dur/step)
    cl = np.zeros((tot_steps, num_classes, max_overlap))
    loc = np.zeros((tot_steps, num_classes, max_overlap, 3))
    #quantize time stamp to step resolution
    quantize = lambda x: round(float(x) / step) * step
    #from quantized time resolution to output frame
    get_frame = lambda x: int(np.interp(x, (0,dur),(0,num_frames-1)))

    df = pd.read_csv(path)
    #print(df)
    for index, s in df.iterrows():  #iterate each sound in the list
        #print (s)
        #compute start and end frame position (quantizing)
        start = quantize(s['Start'])
        end = quantize(s['End'])
        start_frame = get_frame(start)
        end_frame = get_frame(end)
        class_id = class_dict[s['Class']]  #int ID of sound class name
        #print (s['Class'], class_id, start_frame, end_frame)
        #write velues in the output matrix
        sound_frames = np.arange(start_frame, end_frame+1)
        for f in sound_frames:
            pos = int(np.sum(cl[f][class_id])) #how many sounds of current class are present in current frame
            cl[f][class_id][pos] = 1.      #write detection label
            #write loc labels
            loc[f][class_id][pos][0] = s['X']
            loc[f][class_id][pos][1] = s['Y']
            loc[f][class_id][pos][2] = s['Z']
            #print (cl[f][class_id])

    #reshape arrays
    cl = np.reshape(cl, (num_frames, num_classes * max_overlap))
    loc = np.reshape(loc, (num_frames, num_classes * max_overlap * 3))

    loc = loc / max_loc_value  #normalize xyz (to use tanh in the model)

    stacked = np.zeros((cl.shape[0],cl.shape[1]+loc.shape[1]))
    stacked[:,:cl.shape[1]] = cl
    stacked[:,cl.shape[1]:] = loc

    return stacked


def get_label_task2(path,frame_len,file_size,sample_rate,classes_,num_frames,
                    max_label_distance):
    '''
    Process input csv file and output a matrix containing
    the class ids of all sounds present in each data-point and
    their location coordinates, divided in 100 milliseconds frames.
    '''

    class_vec=[]
    loc_vec=[]
    num_classes=len(classes_)
    for k in range(num_frames):
        class_vec.append([None]*num_classes*3)
        loc_vec.append([None]*(num_classes*9))

    class_dict={}
    df=pd.read_csv(path,index_col=False)
    classes_names=classes_
    #classes_names=df['sound_event_recording'].unique()
    #classes_names=classes_names.tolist()
    data_for_class=[]
    for class_name in classes_names:
        class_dict[class_name]=[]
    for class_name in classes_names:
        #data_for_class=df.loc[df['sound_event_recording'] == class_name]
        data_for_class=df.loc[df['Class'] == class_name]
        data_for_class=data_for_class.values.tolist()
        for data in data_for_class:
            class_dict[data[3]].append([data[1],data[2],data[4],data[5],data[6]])

    for j, i in enumerate(np.arange(frame_len,file_size+frame_len,frame_len)):
        start=i-frame_len
        end=i
        for clas in class_dict:
            data_list=class_dict[clas]
            for data in data_list:
                is_in=False
                start_audio=data[0]
                end_audio=data[1]
                x_audio=data[2]
                y_audio=data[3]
                z_audio=data[4]
                if start_audio<start and end_audio>end:
                    is_in=True
                elif end_audio>start and end_audio<end:
                    is_in=True
                elif start_audio>start and start_audio<end:
                    is_in=True
                if is_in:
                    ind_class=classes_names.index(clas)*3
                    if class_vec[j][ind_class]==None:
                        class_vec[j][ind_class]=1
                    elif class_vec[j][ind_class]!=None and class_vec[j][ind_class+1]==None:
                        class_vec[j][ind_class+1]=1
                    else:
                        class_vec[j][ind_class+2]=1
                    if loc_vec[j][ind_class*3]==None:
                        loc_vec[j][0+int(ind_class*3)]=x_audio
                        loc_vec[j][1+int(ind_class*3)]=y_audio
                        loc_vec[j][2+int(ind_class*3)]=z_audio
                    elif loc_vec[j][ind_class*3]!=None and loc_vec[j][ind_class+1]==None:
                        loc_vec[j][3+int(ind_class*3)]=x_audio
                        loc_vec[j][4+int(ind_class*3)]=y_audio
                        loc_vec[j][5+int(ind_class*3)]=z_audio
                    else:
                        loc_vec[j][6+int(ind_class*3)]=x_audio
                        loc_vec[j][7+int(ind_class*3)]=y_audio
                        loc_vec[j][8+int(ind_class*3)]=z_audio
        for i in range(len(loc_vec[j])):
            if loc_vec[j][i]==None:
                loc_vec[j][i]=0
        for i in range(len(class_vec[j])):
            if class_vec[j][i]==None:
                class_vec[j][i]=0

    class_vec = np.array(class_vec)
    loc_vec = np.array(loc_vec)

    loc_vec = loc_vec / max_label_distance  #normalize xyz (to use tanh in the model)

    stacked = np.zeros((class_vec.shape[0],class_vec.shape[1]+loc_vec.shape[1]))
    stacked[:,:class_vec.shape[1]] = class_vec
    stacked[:,class_vec.shape[1]:] = loc_vec
    #return (class_vec), (loc_vec)
    return stacked


def segment_waveforms(predictors, target, length):
    '''
    segment input waveforms into shorter frames of
    predefined length. Output lists of cut frames
    - length is in samples
    '''

    def pad(x, d):
        pad = np.zeros((x.shape[0], d))
        pad[:,:x.shape[-1]] = x
        return pad

    cuts = np.arange(0,predictors.shape[-1], length)  #points to cut
    X = []
    Y = []
    for i in range(len(cuts)):
        start = cuts[i]
        if i != len(cuts)-1:
            end = cuts[i+1]
            cut_x = predictors[:,start:end]
            cut_y = target[:,start:end]
        else:
            end = predictors.shape[-1]
            cut_x = pad(predictors[:,start:end], length)
            cut_y = pad(target[:,start:end], length)
        X.append(cut_x)
        Y.append(cut_y)
    return X, Y

def segment_task2(predictors, target, predictors_len_segment=50*8, target_len_segment=50, overlap=0.5):
    '''
    Segment input stft and target matrix of task 2 into shorter chunks.
    Default parameters cut 5-seconds frames.
    '''

    def pad(x, d):  #3d pad, padding last dim
        pad = np.zeros((x.shape[0], x.shape[1], d))
        pad[:,:,:x.shape[-1]] = x
        return pad

    target = target.reshape(1, target.shape[-1], target.shape[0])  #add dim and invert target dims so that the dim to cut is the same of predictors
    cuts_predictors = np.arange(0,predictors.shape[-1], int(predictors_len_segment*overlap))  #points to cut
    cuts_target = np.arange(0,target.shape[-1], int(target_len_segment*overlap))  #points to cut

    if len(cuts_predictors) != len(cuts_target):
        raise ValueError('Predictors and test frames should be selected to produce the same amount of frames')
    X = []
    Y = []
    for i in range(len(cuts_predictors)):
        start_p = cuts_predictors[i]
        start_t = cuts_target[i]
        end_p = start_p + predictors_len_segment
        end_t = start_t + target_len_segment

        if end_p <= predictors.shape[-1]:  #if chunk is not exceeding buffer size
            cut_x = predictors[:,:,start_p:end_p]
            cut_y = target[:,:,start_t:end_t]
        else: #if exceeding, zero padding is needed
            cut_x = pad(predictors[:,:,start_p:], predictors_len_segment)
            cut_y = pad(target[:,:,start_t:], target_len_segment)

        cut_y = np.reshape(cut_y, (cut_y.shape[-1], cut_y.shape[1]))  #unsqueeze and revert

        X.append(cut_x)
        Y.append(cut_y)

        #print (start_p, end_p, '|', start_t, end_t)
        #print (cut_x.shape, cut_y.shape)

    return X, Y

def gen_seld_out(n_frames, n_overlaps=3, n_classes=14):
    '''
    generate a fake output of the seld model
    ***only for testing
    '''
    results = []
    for frame in range(n_frames):
        n_sounds = np.random.randint(4)
        for i in range(n_sounds):
            t_class = np.random.randint(n_classes)
            tx = (np.random.sample() * 4) - 2
            ty = ((np.random.sample() * 2) - 1) * 1.5
            tz = (np.random.sample() * 2) - 1
            temp_entry = [frame, t_class, tx, ty, tz]
            #print (temp_entry)
            results.append(temp_entry)
    results = np.array(results)
    #pd.DataFrame(results).to_csv(out_path, index=None, header=None)
    return results


def gen_dummy_seld_results(out_path, n_frames=10, n_files=30, perc_tp=0.6,
                           n_overlaps=3, n_classes=14):
    '''
    generate a fake pair of seld model output and truth files
    ***only for testing
    '''

    truth_path = os.path.join(out_path, 'truth')
    pred_path = os.path.join(out_path, 'pred')
    if not os.path.exists(truth_path):
        os.makedirs(truth_path)
    if not os.path.exists(pred_path):
        os.makedirs(pred_path)

    for file in range(n_files):
        #generate rtandom prediction and truth files
        pred_results = gen_seld_out(n_frames, n_overlaps, n_classes)
        truth_results = gen_seld_out(n_frames, n_overlaps, n_classes)

        #change a few entries in the pred in order to make them match
        num_truth = len(truth_results)
        num_pred = len(pred_results)
        num_tp = int(num_truth * perc_tp)
        list_entries = list(range(min(num_truth, num_pred)))
        random.shuffle(list_entries)
        truth_ids = list_entries[:num_tp]
        for t in truth_ids:
            pred_results[t] = truth_results[t]

        truth_out_file = os.path.join(truth_path, str(file) + '.csv')
        pred_out_file = os.path.join(pred_path, str(file) + '.csv')

        pd.DataFrame(truth_results).to_csv(truth_out_file, index=None, header=None)
        pd.DataFrame(pred_results).to_csv(pred_out_file, index=None, header=None)


def gen_dummy_waveforms(n, out_path):
    '''
    Generate random waveforms as example for the submission
    '''
    sr = 16000
    max_len = 10  #secs

    for i in range(n):
        len = int(np.random.sample() * max_len * sr)
        sound = ((np.random.sample(len) * 2) - 1) * 0.9
        filename = os.path.join(out_path, str(i) + '.npy')
        np.save(filename, sound)


def gen_fake_task1_dataset():
    l = []
    target = []
    for i in range(4):
        n = 160000
        n_target = 160000
        sig = np.random.sample(n)
        sig_target = np.random.sample(n_target).reshape((1, n_target))
        target.append(sig_target)
        sig = np.vstack((sig,sig,sig,sig))
        l.append(sig)

    output_path = '../prova_pickle'
    if not os.path.isdir(output_path):
        os.mkdir(output_path)

    with open(os.path.join(output_path,'training_predictors.pkl'), 'wb') as f:
        pickle.dump(l, f)
    with open(os.path.join(output_path,'training_target.pkl'), 'wb') as f:
        pickle.dump(target, f)
    with open(os.path.join(output_path,'validation_predictors.pkl'), 'wb') as f:
        pickle.dump(l, f)
    with open(os.path.join(output_path,'validation_target.pkl'), 'wb') as f:
        pickle.dump(target, f)
    with open(os.path.join(output_path,'test_predictors.pkl'), 'wb') as f:
        pickle.dump(l, f)
    with open(os.path.join(output_path,'test_target.pkl'), 'wb') as f:
        pickle.dump(target, f)
    '''
    np.save(os.path.join(output_path,'training_predictors.npy'), l)
    np.save(os.path.join(output_path,'training_target.npy'), l)
    np.save(os.path.join(output_path,'validation_predictors.npy'), l)
    np.save(os.path.join(output_path,'validation_target.npy'), l)
    np.save(os.path.join(output_path,'test_predictors.npy'), l)
    np.save(os.path.join(output_path,'test_target.npy'), l)
    '''

    with open(os.path.join(output_path,'training_predictors.pkl'), 'rb') as f:
        data = pickle.load(f)
    with open(os.path.join(output_path,'training_target.pkl'), 'rb') as f:
        data2 = pickle.load(f)

    print (data[0].shape)
    print (data2[0].shape)
