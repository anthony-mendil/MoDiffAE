import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import clip
from model.rotation2xyz import Rotation2xyz


class MDM(nn.Module):
    def __init__(self, modeltype, njoints, nfeats, num_actions, num_frames, translation, pose_rep, glob, glob_rot,
                 latent_dim=256, ff_size=1024, num_layers=8, num_heads=4, dropout=0.1, #semantic_dim=512,
                 ablation=None, activation="gelu", legacy=False, data_rep='rot6d', dataset='amass', clip_dim=512,
                 arch='trans_enc', emb_trans_dec=False, clip_version=None, **kargs):
        super().__init__()

        self.legacy = legacy
        self.modeltype = modeltype
        self.njoints = njoints
        self.nfeats = nfeats
        self.num_actions = num_actions
        self.data_rep = data_rep
        self.dataset = dataset

        self.pose_rep = pose_rep
        self.glob = glob
        self.glob_rot = glob_rot
        self.translation = translation

        self.latent_dim = latent_dim
        #self.semantic_dim = semantic_dim
        self.num_frames = num_frames

        self.ff_size = ff_size
        self.num_layers = num_layers
        self.num_heads = num_heads
        self.dropout = dropout

        self.ablation = ablation
        self.activation = activation
        self.clip_dim = clip_dim
        self.action_emb = kargs.get('action_emb', None)

        self.input_feats = self.njoints * self.nfeats

        self.normalize_output = kargs.get('normalize_encoder_output', False)

        self.cond_mode = kargs.get('cond_mode', 'no_cond')
        self.cond_mask_prob = kargs.get('cond_mask_prob', 0.)
        self.arch = arch
        self.gru_emb_dim = self.latent_dim if self.arch == 'gru' else 0
        self.input_process = InputProcess(self.data_rep, self.input_feats+self.gru_emb_dim, self.latent_dim)

        self.sequence_pos_encoder = PositionalEncoding(self.latent_dim, self.dropout)
        self.emb_trans_dec = emb_trans_dec

        if self.arch == 'trans_enc':
            print("TRANS_ENC init")
            seqTransEncoderLayer = nn.TransformerEncoderLayer(d_model=self.latent_dim,
                                                              nhead=self.num_heads,
                                                              dim_feedforward=self.ff_size,
                                                              dropout=self.dropout,
                                                              activation=self.activation)

            self.seqTransEncoder = nn.TransformerEncoder(seqTransEncoderLayer,
                                                         num_layers=self.num_layers)

            # Testing out
            seq_trans_encoder_layer_semantic = nn.TransformerEncoderLayer(d_model=self.latent_dim,
                                                                 nhead=self.num_heads,
                                                                 dim_feedforward=self.ff_size,
                                                                 dropout=self.dropout,
                                                                 activation=self.activation)

            self.seqTransEncoder_semantic = nn.TransformerEncoder(seq_trans_encoder_layer_semantic,
                                                         num_layers=self.num_layers)

            self.linear_time = nn.Linear(
                in_features=self.num_frames,
                out_features=1
            )

        elif self.arch == 'trans_dec':
            print("TRANS_DEC init")
            seqTransDecoderLayer = nn.TransformerDecoderLayer(d_model=self.latent_dim,
                                                              nhead=self.num_heads,
                                                              dim_feedforward=self.ff_size,
                                                              dropout=self.dropout,
                                                              activation=activation)
            self.seqTransDecoder = nn.TransformerDecoder(seqTransDecoderLayer,
                                                         num_layers=self.num_layers)
        elif self.arch == 'gru':
            print("GRU init")
            self.gru = nn.GRU(self.latent_dim, self.latent_dim, num_layers=self.num_layers, batch_first=True)
        else:
            raise ValueError('Please choose correct architecture [trans_enc, trans_dec, gru]')

        self.embed_timestep = TimestepEmbedder(self.latent_dim, self.sequence_pos_encoder)

        if self.cond_mode != 'no_cond':
            if 'text' in self.cond_mode:
                self.embed_text = nn.Linear(self.clip_dim, self.latent_dim)
                print('EMBED TEXT')
                print('Loading CLIP...')
                self.clip_version = clip_version
                self.clip_model = self.load_and_freeze_clip(clip_version)
            if 'action' in self.cond_mode:
                self.embed_action = EmbedAction(self.num_actions, self.latent_dim)
                print('EMBED ACTION')

            #self.semantic_encoder = SemanticEncoder(
            #    data_rep=self.data_rep,
            #    input_feats=self.input_feats,
            #    num_frames=self.num_frames,
            #    latent_dim=self.latent_dim,
            #    num_heads=self.num_heads,
            #    ff_size=self.ff_size,
            #    dropout=self.dropout,
            #    activation=self.activation,
            #    num_layers=self.num_layers#,
            #    #semantic_dim=self.semantic_dim
            #)

        self.output_process = OutputProcess(self.data_rep, self.input_feats, self.latent_dim, self.njoints,
                                            self.nfeats)

        # self.rot2xyz = Rotation2xyz(device='cpu', dataset=self.dataset)
        self.rot2xyz = Rotation2xyz()   # device='cpu')  # , dataset=self.dataset)

    def parameters_wo_clip(self):
        return [p for name, p in self.named_parameters() if not name.startswith('clip_model.')]

    def load_and_freeze_clip(self, clip_version):
        clip_model, clip_preprocess = clip.load(clip_version, device='cpu',
                                                jit=False)  # Must set jit=False for training
        clip.model.convert_weights(
            clip_model)  # Actually this line is unnecessary since clip by default already on float16

        # Freeze CLIP weights
        clip_model.eval()
        for p in clip_model.parameters():
            p.requires_grad = False

        return clip_model

    def mask_cond(self, cond, force_mask=False):
        bs, d = cond.shape
        if force_mask:
            return torch.zeros_like(cond)
        elif self.training and self.cond_mask_prob > 0.:
            mask = torch.bernoulli(torch.ones(bs, device=cond.device) * self.cond_mask_prob).view(bs, 1)  # 1-> use null_cond, 0-> use real cond
            return cond * (1. - mask)
        else:
            return cond

    def encode_text(self, raw_text):
        # raw_text - list (batch_size length) of strings with input text prompts
        device = next(self.parameters()).device
        max_text_len = 20 if self.dataset in ['humanml', 'kit'] else None  # Specific hardcoding for humanml dataset
        if max_text_len is not None:
            default_context_length = 77
            context_length = max_text_len + 2 # start_token + 20 + end_token
            assert context_length < default_context_length
            texts = clip.tokenize(raw_text, context_length=context_length, truncate=True).to(device) # [bs, context_length] # if n_tokens > context_length -> will truncate
            # print('texts', texts.shape)
            zero_pad = torch.zeros([texts.shape[0], default_context_length-context_length], dtype=texts.dtype, device=texts.device)
            texts = torch.cat([texts, zero_pad], dim=1)
            # print('texts after pad', texts.shape, texts)
        else:
            texts = clip.tokenize(raw_text, truncate=True).to(device) # [bs, context_length] # if n_tokens > 77 -> will truncate
        return self.clip_model.encode_text(texts).float()

    def encode_semantic(self, og_motion):
        # Anthony: using weight sharing for this layer (all the pose embeddings should share weights)

        og_motion = self.input_process(og_motion)
        og_motion = self.sequence_pos_encoder(og_motion)

        #print(og_motion[0])

        # semantic_emb = self.semantic_encoder(y['original_motion'])
        semantic_emb = self.seqTransEncoder_semantic(og_motion)

        #print(semantic_emb[0])
        #exit()

        semantic_emb = semantic_emb.transpose(2, 0)
        semantic_emb = self.linear_time(semantic_emb).squeeze().transpose(1, 0)
        return semantic_emb

    def forward(self, x, timesteps, y=None):
        """
        x: [batch_size, njoints, nfeats, max_frames], denoted x_t in the paper
        timesteps: [batch_size] (int)
        """
        bs, njoints, nfeats, nframes = x.shape
        emb = self.embed_timestep(timesteps)  # [1, bs, d]

        # trying out semantic encoder
        #semantic_code = self.semantic_encoder(x)
        #print(semantic_code.shape)
        #exit()
        #print(emb)
        #print(emb.shape)

        force_mask = y.get('uncond', False)
        #if 'text' in self.cond_mode:
        #    enc_text = self.encode_text(y['text'])
        #    emb += self.embed_text(self.mask_cond(enc_text, force_mask=force_mask))
        #if 'action' in self.cond_mode:
        #    action_emb = self.embed_action(y['action'])
        #    emb += self.mask_cond(action_emb, force_mask=force_mask)

        #print(y['original_sequence'])
        #print(y['original_sequence'].shape)

        #print(x.shape)
        #print(x)
        #print(timesteps)
        #exit()

        #semantic_emb = self.semantic_encoder(x)

        #print(y['original_motion'])
        og_motion = y['original_motion']

        '''
        og_motion = self.input_process(og_motion)
        og_motion = self.sequence_pos_encoder(og_motion)

        #semantic_emb = self.semantic_encoder(y['original_motion'])
        semantic_emb = self.seqTransEncoder_semantic(og_motion)
        semantic_emb = semantic_emb.transpose(2, 0)
        semantic_emb = self.linear_time(semantic_emb).squeeze().transpose(1, 0)
        '''
        semantic_emb = self.encode_semantic(og_motion)

        #print(semantic_emb)
        #print('hi')
        #exit()

        emb += self.mask_cond(semantic_emb, force_mask=force_mask)

        #print('using semantic embedding')

        #print(emb)
        #print(emb.shape)
        #exit()

        if self.arch == 'gru':
            x_reshaped = x.reshape(bs, njoints*nfeats, 1, nframes)
            emb_gru = emb.repeat(nframes, 1, 1)     #[#frames, bs, d]
            emb_gru = emb_gru.permute(1, 2, 0)      #[bs, d, #frames]
            emb_gru = emb_gru.reshape(bs, self.latent_dim, 1, nframes)  #[bs, d, 1, #frames]
            x = torch.cat((x_reshaped, emb_gru), axis=1)  #[bs, d+joints*feat, 1, #frames]

        x = self.input_process(x)

        if self.arch == 'trans_enc':
            # adding the timestep embed
            xseq = torch.cat((emb, x), axis=0)  # [seqlen+1, bs, d]
            xseq = self.sequence_pos_encoder(xseq)  # [seqlen+1, bs, d]

            #print(xseq.shape)
            output = self.seqTransEncoder(xseq)[1:]  # , src_key_padding_mask=~maskseq)  # [seqlen, bs, d]
            #print(output.shape)
            #exit()

        elif self.arch == 'trans_dec':
            if self.emb_trans_dec:
                xseq = torch.cat((emb, x), axis=0)
            else:
                xseq = x
            xseq = self.sequence_pos_encoder(xseq)  # [seqlen+1, bs, d]
            if self.emb_trans_dec:
                output = self.seqTransDecoder(tgt=xseq, memory=emb)[1:] # [seqlen, bs, d] # FIXME - maybe add a causal mask
            else:
                output = self.seqTransDecoder(tgt=xseq, memory=emb)
        elif self.arch == 'gru':
            xseq = x
            xseq = self.sequence_pos_encoder(xseq)  # [seqlen, bs, d]
            output, _ = self.gru(xseq)

        output = self.output_process(output)  # [bs, njoints, nfeats, nframes]
        return output


    # Anthony: not using smpl model
    def _apply(self, fn):
        super()._apply(fn)
        #self.rot2xyz.smpl_model._apply(fn)

    # Anthony: not using smpl model
    def train(self, *args, **kwargs):
        super().train(*args, **kwargs)
        #self.rot2xyz.smpl_model.train(*args, **kwargs)


class PositionalEncoding(nn.Module):
    def __init__(self, d_model, dropout=0.1, max_len=5000):
        super(PositionalEncoding, self).__init__()
        self.dropout = nn.Dropout(p=dropout)

        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-np.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0).transpose(0, 1)

        self.register_buffer('pe', pe)

    def forward(self, x):
        # not used in the final model
        x = x + self.pe[:x.shape[0], :]
        return self.dropout(x)


class TimestepEmbedder(nn.Module):
    def __init__(self, latent_dim, sequence_pos_encoder):
        super().__init__()
        self.latent_dim = latent_dim
        self.sequence_pos_encoder = sequence_pos_encoder

        time_embed_dim = self.latent_dim
        self.time_embed = nn.Sequential(
            nn.Linear(self.latent_dim, time_embed_dim),
            nn.SiLU(),
            nn.Linear(time_embed_dim, time_embed_dim),
        )

    def forward(self, timesteps):
        return self.time_embed(self.sequence_pos_encoder.pe[timesteps]).permute(1, 0, 2)


class InputProcess(nn.Module):
    def __init__(self, data_rep, input_feats, latent_dim):
        super().__init__()
        self.data_rep = data_rep
        self.input_feats = input_feats
        self.latent_dim = latent_dim
        self.poseEmbedding = nn.Linear(self.input_feats, self.latent_dim)
        if self.data_rep == 'rot_vel':
            self.velEmbedding = nn.Linear(self.input_feats, self.latent_dim)

    def forward(self, x):
        bs, njoints, nfeats, nframes = x.shape
        x = x.permute((3, 0, 1, 2)).reshape(nframes, bs, njoints*nfeats)

        if self.data_rep in ['rot6d', 'xyz', 'hml_vec']:
            x = self.poseEmbedding(x)  # [seqlen, bs, d]
            return x
        elif self.data_rep == 'rot_vel':
            first_pose = x[[0]]  # [1, bs, 150]
            first_pose = self.poseEmbedding(first_pose)  # [1, bs, d]
            vel = x[1:]  # [seqlen-1, bs, 150]
            vel = self.velEmbedding(vel)  # [seqlen-1, bs, d]
            return torch.cat((first_pose, vel), axis=0)  # [seqlen, bs, d]
        else:
            raise ValueError


class OutputProcess(nn.Module):
    def __init__(self, data_rep, input_feats, latent_dim, njoints, nfeats):
        super().__init__()
        self.data_rep = data_rep
        self.input_feats = input_feats
        self.latent_dim = latent_dim
        self.njoints = njoints
        self.nfeats = nfeats
        self.poseFinal = nn.Linear(self.latent_dim, self.input_feats)
        if self.data_rep == 'rot_vel':
            self.velFinal = nn.Linear(self.latent_dim, self.input_feats)

    def forward(self, output):
        nframes, bs, d = output.shape
        if self.data_rep in ['rot6d', 'xyz', 'hml_vec']:
            output = self.poseFinal(output)  # [seqlen, bs, 150]
        elif self.data_rep == 'rot_vel':
            first_pose = output[[0]]  # [1, bs, d]
            first_pose = self.poseFinal(first_pose)  # [1, bs, 150]
            vel = output[1:]  # [seqlen-1, bs, d]
            vel = self.velFinal(vel)  # [seqlen-1, bs, 150]
            output = torch.cat((first_pose, vel), axis=0)  # [seqlen, bs, 150]
        else:
            raise ValueError
        output = output.reshape(nframes, bs, self.njoints, self.nfeats)
        output = output.permute(1, 2, 3, 0)  # [bs, njoints, nfeats, nframes]
        return output


class EmbedAction(nn.Module):
    def __init__(self, num_actions, latent_dim):
        super().__init__()
        self.action_embedding = nn.Parameter(torch.randn(num_actions, latent_dim))

    def forward(self, input):
        idx = input[:, 0].to(torch.long)  # an index array must be long
        output = self.action_embedding[idx]
        return output


# This is just to test if the semantic encoder works if trained
# directly for classification. This should show if there is a problem with the system / lr
# or the data itself.
class SemanticEncoder(nn.Module):
    def __init__(self, data_rep, input_feats, num_frames, latent_dim=256, ff_size=1024, num_layers=8,
                 num_heads=4, dropout=0.1, activation="gelu"):   # , semantic_dim=256):
        super().__init__()

        self.latent_dim = latent_dim
        self.num_heads = num_heads
        self.ff_size = ff_size
        self.dropout = dropout
        self.activation = activation
        self.num_layers = num_layers
        #self.semantic_dim = semantic_dim
        self.num_frames = num_frames

        self.data_rep = data_rep
        self.input_feats = input_feats
        #self.gru_emb_dim = gru_emb_dim

        self.input_process = InputProcess(self.data_rep, self.input_feats, self.latent_dim)

        self.sequence_pos_encoder = PositionalEncoding(self.latent_dim, self.dropout)

        seq_trans_encoder_layer = nn.TransformerEncoderLayer(d_model=self.latent_dim,
                                                             nhead=self.num_heads,
                                                             dim_feedforward=self.ff_size,
                                                             dropout=self.dropout,
                                                             activation=self.activation)

        self.seqTransEncoder = nn.TransformerEncoder(seq_trans_encoder_layer,
                                                     num_layers=self.num_layers)

        #self.linear_latent = nn.Linear(
        #    in_features=self.latent_dim,
        #    out_features=self.semantic_dim
        #)

        self.linear_time = nn.Linear(
            in_features=self.num_frames,
            out_features=1
        )

        self.linear_sem = torch.nn.Linear(
            in_features=512,
            out_features=5
        )

    def forward(self, x):

        x = self.input_process(x)

        #print(x)

        x_seq = self.sequence_pos_encoder(x)  # [seqlen, bs, d]

        print(x_seq)
        # TODO: problem: for some reason the this outputs the same values for all inputs in a batch
        encoder_output = self.seqTransEncoder(x_seq)   # [seqlen, bs, d]

        print(encoder_output)
        #exit()

        #print(encoder_output.shape)
        #output = self.linear_latent(encoder_output)   # [seqlen, bs, semdim]
        output = encoder_output.transpose(2, 0)   # # [semdim, bs, seqlen]

        #print(output)

        #print(output.shape)
        output = self.linear_time(output).squeeze().transpose(1, 0)   # [bs, semdim]

        output = self.linear_sem(output)

        # print(x)
        sm = nn.Softmax(dim=-1)
        output = sm(output)

        return output

