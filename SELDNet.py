import torch
import torch.nn as nn
import torch.nn.functional as F
import os
import numpy as np
from utility_tac.models import *
from torchvision import models
import utility_functions as uf

'''
Pytorch implementation of SELDNet: https://arxiv.org/pdf/1807.00129.pdf
'''

class Fake_Seldnet(nn.Module):
    def __init__(self, dropout_perc=0.5):
        super(Fake_Seldnet, self).__init__()
        self.feat_extraction = models.vgg16.feature()

        model.features[0] = nn.Conv2d(1, 64, kernel_size=(3, 3),
                                stride=(1, 1), padding=(1, 1))

                                #change num output classes
        model.classifier[6] =nn.Linear(in_features=4096,
                                out_features=p['output_classes'], bias=True)

    def forward(x,self):
        x = self.features(x)
        return x


class Seldnet(nn.Module):
    def __init__(self, time_dim, freq_dim=256, input_channels=8, output_classes=14,
                 pool_size=[[8,2],[8,2],[2,2]], pool_time=False,  n_cnn_filters=64,
                 rnn_size=128, n_rnn=2,fc_size=128, dropout_perc=0., verbose=False):
        super(Seldnet, self).__init__()
        self.verbose = verbose
        self.time_dim = time_dim
        self.freq_dim = freq_dim
        doa_output_size = output_classes * 3    #here 3 is the max number of simultaneus sounds from the same class
        sed_output_size = doa_output_size * 3   #here 3 is the number of spatial dimensions xyz
        if pool_time:
            self.time_pooled_size = int(time_dim / np.prod(np.array(pool_size), axis=0)[-1])
        else:
            self.time_pooled_size = time_dim
        #building CNN feature extractor
        conv_layers = []
        in_chans = input_channels
        for p in pool_size:
            curr_chans = n_cnn_filters
            if pool_time:
                pool = [p[0],p[1]]
            else:
                pool = [p[0],1]
            conv_layers.append(
                nn.Sequential(
                    nn.Conv2d(in_chans, out_channels=curr_chans,
                                kernel_size=3, stride=1, padding=1),  #padding 1 = same with kernel = 3
                    nn.BatchNorm2d(n_cnn_filters),
                    nn.ReLU(),
                    nn.MaxPool2d(pool),
                    nn.Dropout(dropout_perc)))
            in_chans = curr_chans

        self.cnn = nn.Sequential(*conv_layers)

        self.rnn = nn.GRU(128, rnn_size, num_layers=n_rnn, batch_first=True,
                          bidirectional=True, dropout=dropout_perc)

        self.sed = nn.Sequential(
                    nn.Linear(256, fc_size),
                    nn.Dropout(dropout_perc),
                    nn.Linear(fc_size, doa_output_size),
                    nn.Sigmoid())

        self.doa = nn.Sequential(
                    nn.Linear(256, fc_size),
                    nn.Dropout(dropout_perc),
                    nn.Linear(fc_size, sed_output_size),
                    nn.Tanh())

    def forward(self, x):
        x = self.cnn(x)
        if self.verbose:
            print ('cnn out ', x.shape)    #target dim: [batch, n_cnn_filters, 2, time_frames]
        x = x.permute(0,3,1,2) #[batch, time, channels, freq]
        if self.verbose:
            print ('permuted: ', x.shape)    #target dim: [batch, time_frames, n_cnn_filters, 2]
        x = x.reshape(x.shape[0], self.time_pooled_size, -1)
        if self.verbose:
            print ('reshaped: ', x.shape)    #target dim: [batch, 2*n_cnn_filters]
        x, h = self.rnn(x)
        if self.verbose:
            print ('rnn out:  ', x.shape)    #target dim: [batch, 2*n_cnn_filters]
        sed = self.sed(x)
        doa = self.doa(x)
        if self.verbose:
            print ('sed prediction:  ', sed.shape)  #target dim: [batch, time, sed_output_size]
            print ('doa prediction: ', doa.shape)  #target dim: [batch, time, doa_output_size]

        return sed, doa

class Seldnet_augmented(nn.Module):
    def __init__(self, time_dim, freq_dim=256, input_channels=4, output_classes=14,
                 pool_size=[[8,2],[8,2],[2,2],[1,1]], cnn_filters=[64,128,256,512], pool_time=True,
                 rnn_size=256, n_rnn=3, fc_size=1024, dropout_perc=0.3, verbose=False):
        super(Seldnet_augmented, self).__init__()
        self.verbose = verbose
        self.time_dim = time_dim
        self.freq_dim = freq_dim
        doa_output_size = output_classes * 3    #here 3 is the max number of simultaneus sounds from the same class
        sed_output_size = doa_output_size * 3   #here 3 is the number of spatial dimensions xyz
        if pool_time:
            self.time_pooled_size = int(time_dim / np.prod(np.array(pool_size), axis=0)[-1])
        else:
            self.time_pooled_size = time_dim
        #building CNN feature extractor
        conv_layers = []
        in_chans = input_channels
        for i, (p,c) in enumerate(zip(pool_size, cnn_filters)):
            curr_chans = c

            if pool_time:
                pool = [p[0],p[1]]
            else:
                pool = [p[0],1]
            conv_layers.append(
                nn.Sequential(
                    nn.Conv2d(in_chans, out_channels=curr_chans,
                                kernel_size=3, stride=1, padding=1),  #padding 1 = same with kernel = 3
                    nn.BatchNorm2d(c),
                    nn.ReLU(),
                    nn.MaxPool2d(pool),
                    nn.Dropout(dropout_perc)))
            in_chans = curr_chans

        self.cnn = nn.Sequential(*conv_layers)

        self.rnn = nn.GRU(1024, rnn_size, num_layers=n_rnn, batch_first=True,
                          bidirectional=True, dropout=dropout_perc)

        self.sed = nn.Sequential(
                    nn.Linear(rnn_size*2, fc_size),
                    nn.ReLU(),
                    nn.Linear(fc_size, fc_size),
                    nn.ReLU(),
                    nn.Linear(fc_size, fc_size),
                    nn.ReLU(),
                    nn.Dropout(dropout_perc),
                    nn.Linear(fc_size, doa_output_size),
                    nn.Sigmoid())

        self.doa = nn.Sequential(
                    nn.Linear(rnn_size*2, fc_size),
                    nn.ReLU(),
                    nn.Linear(fc_size, fc_size),
                    nn.ReLU(),
                    nn.Linear(fc_size, fc_size),
                    nn.ReLU(),
                    nn.Dropout(dropout_perc),
                    nn.Linear(fc_size, sed_output_size),
                    nn.Tanh())

    def forward(self, x):
        x = self.cnn(x)
        if self.verbose:
            print ('cnn out ', x.shape)    #target dim: [batch, n_cnn_filters, 2, time_frames]
        x = x.permute(0,3,1,2) #[batch, time, channels, freq]
        if self.verbose:
            print ('permuted: ', x.shape)    #target dim: [batch, time_frames, n_cnn_filters, 2]
        x = x.reshape(x.shape[0], self.time_pooled_size, -1)
        if self.verbose:
            print ('reshaped: ', x.shape)    #target dim: [batch, 2*n_cnn_filters]
        x, h = self.rnn(x)
        if self.verbose:
            print ('rnn out:  ', x.shape)    #target dim: [batch, 2*n_cnn_filters]
        sed = self.sed(x)
        doa = self.doa(x)
        if self.verbose:
            print ('sed prediction:  ', sed.shape)  #target dim: [batch, time, sed_output_size]
            print ('doa prediction: ', doa.shape)  #target dim: [batch, time, doa_output_size]

        return sed, doa

def test_model():
    '''
    Test model's i/o shapes with the default prepocessing parameters
    '''
    #create dummy input spectrogram
    sample = np.ones((4,32000*60))
    nperseg = 512
    noverlap = 112
    sp = uf.spectrum_fast(sample, nperseg=nperseg, noverlap=noverlap, output_phase=False)
    sp = torch.tensor(sp.reshape(1,sp.shape[0],sp.shape[1],sp.shape[2])).float()
    #sp = sp[:,:,:,:50*8]  #segmented dimension

    #create model
    #the dimension of the input spectrogram and the pooling/processing dimension of the model
    #create 1 prediction (sed and doa) for each 100-milliseconds label frame
    model = Seldnet_augmented(sp.shape[-1],pool_time=True, verbose=True)
    print (model)
    print ('Input shape: ', sp.shape)
    sed, doa = model(sp)
    print ('SED shape: ', sed.shape, "| DOA shape: ", doa.shape)    #target shape sed=[batch,600(label frames),42] doa=[batch, 600(label frames),126

if __name__ == '__main__':
    test_model()
