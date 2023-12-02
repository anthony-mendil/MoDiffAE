from argparse import ArgumentParser
import argparse
import os
import json


def parse_and_load_from_model(parser, model_type, model_path):

    group_names = ['dataset', model_type]

    # args according to the loaded model
    # do not try to specify them from cmd line since they will be overwritten
    add_data_options(parser)

    if model_type == "modiffae":
        add_diffusion_options(parser)
        group_names.append('diffusion')
        add_modiffae_model_options(parser)
    elif model_type == "semantic_generator":
        add_diffusion_options(parser)
        group_names.append('diffusion')
        add_semantic_generator_model_options(parser)
    elif model_type == "semantic_regressor":
        add_semantic_regressor_model_options(parser)
    else:
        print(f'Warning: model type {model_type} is unknown.')

    args, _ = parser.parse_known_args()
    #args = parser.parse_args()
    args_to_overwrite = []
    for group_name in group_names: #['dataset', 'diffusion', model_type]:
        args_to_overwrite += get_args_per_group_name(parser, args, group_name)

    # load args from model
    if model_path is None:
        model_path = get_model_path_from_args(model_type)

    args_path = os.path.join(os.path.dirname(model_path), 'args.json')

    assert os.path.exists(args_path), 'Arguments json file was not found!'
    with open(args_path, 'r') as fr:
        model_args = json.load(fr)

    for a in args_to_overwrite:
        if a in model_args.keys():
            setattr(args, a, model_args[a])

        #elif 'cond_mode' in model_args: # backward compitability
        #    unconstrained = (model_args['cond_mode'] == 'no_cond')
        #    setattr(args, 'unconstrained', unconstrained)

        else:
            print('Warning: was not able to load [{}], using default value [{}] instead.'.format(a, args.__dict__[a]))

    #if args.cond_mask_prob == 0:
    #    args.guidance_param = 1
    return args


def get_args_per_group_name(parser, args, group_name):
    for group in parser._action_groups:
        if group.title == group_name:
            group_dict = {a.dest: getattr(args, a.dest, None) for a in group._group_actions}
            return list(argparse.Namespace(**group_dict).__dict__.keys())
    return ValueError('group_name was not found.')


def get_model_path_from_args(model_type):
    try:
        dummy_parser = ArgumentParser()
        dummy_parser.add_argument(f'--{model_type}_model_path')
        dummy_args, _ = dummy_parser.parse_known_args()
        #return dummy_args.model_path
        model_path = getattr(dummy_args, f'{model_type}_model_path')
        if model_path is None:
            raise ValueError(f'{model_type}_model_path argument must be specified.')
        else:
            return getattr(dummy_args, f'{model_type}_model_path')
    except Exception:
        raise ValueError(f'{model_type}_model_path argument must be specified.')


def add_base_options(parser):
    group = parser.add_argument_group('base')
    group.add_argument("--cuda", default=True, type=bool, help="Use cuda device, otherwise use CPU.")
    group.add_argument("--device", default=0, type=int, help="Device id to use.")
    group.add_argument("--seed", default=10, type=int, help="For fixing random seed.")
    group.add_argument("--batch_size", default=64, type=int, help="Batch size during training.")
    group.add_argument("--num_frames", default=100, type=int, help="Limit for the maximal number of frames.")


def add_diffusion_options(parser):
    group = parser.add_argument_group('diffusion')
    group.add_argument("--noise_schedule", default='cosine', choices=['linear', 'cosine'], type=str,
                       help="Noise schedule type")
    group.add_argument("--diffusion_steps", default=1000, type=int,
                       help="Number of diffusion steps (denoted T in the paper)")
    group.add_argument("--sigma_small", default=True, type=bool, help="Use smaller sigma values.")


def add_data_options(parser):
    group = parser.add_argument_group('dataset')
    group.add_argument("--dataset", default='karate', choices=['karate', 'humanact12'], type=str,
                       help="Dataset name (choose from list).")
    group.add_argument("--test_participant", default='b0372', choices=['b0372', 'b0401'], type=str,
                       help="Test participant. This decides which training and validation data is used.")
    group.add_argument("--pose_rep", default='xyz', choices=['xyz', 'rot_6d', 'rot_vec', 'rot_mat', 'rot_quat'],
                       type=str, help="Pose representation (choose from list).")
    group.add_argument("--no_translation", action='store_true',
                       help="If set, no translation will be used.")
    #group.add_argument("--data_dir", default="", type=str,
    #                   help="If empty, will use defaults according to the specified dataset.")


def add_modiffae_model_options(parser):
    group = parser.add_argument_group('modiffae')
    group.add_argument("--layers", default=8, type=int,
                       help="Number of layers.")
    group.add_argument("--heads", default=4, type=int,
                       help="Number of heads.")
    group.add_argument("--modiffae_latent_dim", default=512, type=int,
                       help="Transformer width.")
    group.add_argument("--transformer_feedforward_dim", default=1024, type=int,
                       help="Transformer width.")
    group.add_argument("--dropout", default=0.1, type=float,
                       help="Dropout rate.")
    group.add_argument("--semantic_pool_type", default='global_max_pool',
                       choices=['global_avg_pool', 'global_max_pool', 'linear_time_layer'], type=str,
                       help="Type of pooling to extract the semantic embedding from the semantic encoder output.")


def add_semantic_generator_model_options(parser):
    group = parser.add_argument_group('semantic_generator')
    # TODO: in paper they used 10 layers
    group.add_argument("--layers", default=10, type=int,  # previously 8
                       help="Number of layers.")
    # TODO: try 1024 or like in paper 2048
    group.add_argument("--semantic_generator_latent_dim", default=2048, type=int,  # previously 512
                       help="Transformer width.")
    group.add_argument("--modiffae_latent_dim", default=512, type=int,
                       help="Transformer width.")
    group.add_argument("--attribute_dim", default=6, type=int,
                       help="Number of attributes.")
    group.add_argument("--dropout", default=0.1, type=float,
                       help="Dropout rate.")


def add_semantic_regressor_model_options(parser):
    group = parser.add_argument_group('semantic_regressor')
    group.add_argument("--modiffae_latent_dim", default=512, type=int,
                       help="Transformer width.")
    group.add_argument("--attribute_dim", default=6, type=int,
                       help="Number of attributes.")


def add_modiffae_training_options(parser):
    group = parser.add_argument_group('modiffae_training')
    group.add_argument("--lambda_rcxyz", default=1, type=float, help="Joint positions loss.")
    group.add_argument("--lambda_vel", default=1, type=float, help="Joint velocity loss.")
    group.add_argument("--lambda_fc", default=1, type=float, help="Foot contact loss.")
    group.add_argument("--model_type", default='modiffae',
                       choices=['modiffae', 'semantic_regressor', 'semantic_generator'], type=str,
                       help="Different components of the system.")
    group.add_argument("--save_dir", required=True, type=str,
                       help="Path to save checkpoints and results.")
    group.add_argument("--overwrite", action='store_true',
                       help="If True, will enable to use an already existing save_dir.")
    group.add_argument("--lr", default=1e-4, type=float, help="General learning rate.")
    group.add_argument("--semantic_encoder_lr", default=1e-5, type=float, help="Learning rate of sematic encoder.")
    group.add_argument("--weight_decay", default=0.0, type=float, help="Optimizer weight decay.")
    #group.add_argument("--lr_anneal_steps", default=0, type=int, help="Number of learning rate anneal steps.")
    group.add_argument("--eval_batch_size", default=32, type=int,
                       help="Batch size during evaluation loop. Do not change this unless you know what you are doing. "
                            "T2m precision calculation is based on fixed batch size 32.")
    group.add_argument("--eval_split", default='test', choices=['val', 'test'], type=str,
                       help="Which split to evaluate on during training.")
    group.add_argument("--eval_during_training", action='store_true',
                       help="If True, will run evaluation during training.")
    group.add_argument("--eval_rep_times", default=3, type=int,
                       help="Number of repetitions for evaluation loop during training.")
    group.add_argument("--eval_num_samples", default=1_000, type=int,
                       help="If -1, will use all samples in the specified split.")
    group.add_argument("--log_interval", default=1_000, type=int,
                       help="Log losses each N steps")
    group.add_argument("--save_interval", default=50_000, type=int,
                       help="Save checkpoints and run evaluation each N steps")
    # TODO: I think 1M steps might be justified. humanAct is 750k steps and 1.2k data, uestc is 2M steps and 5k data
    group.add_argument("--num_steps", default=1_000_000, type=int,
                       help="Training will stop after the specified number of steps.")
    #group.add_argument("--num_steps", default=600_000, type=int,
    #                   help="Training will stop after the specified number of steps.")
    group.add_argument("--resume_checkpoint", default="", type=str,
                       help="If not empty, will start from the specified checkpoint (path to model###.pt file).")


def add_semantic_generator_training_options(parser):
    group = parser.add_argument_group('semantic_generator_training')
    group.add_argument("--model_type", default='modiffae',
                       choices=['modiffae', 'semantic_regressor', 'semantic_generator'], type=str,
                       help="Different components of the system.")
    #group.add_argument("--modiffae_model_path", required=True, type=str,
    #                   help="Path to model####.pt file to be sampled.")
    #base_dir, _ = os.path.split(os.path.dirname(get_model_path_from_args("modiffae")))
    #group.add_argument("--save_dir", default=os.path.join(base_dir, "semantic_generator"), type=str,
    #                   help="Path to save checkpoints and results.")
    group.add_argument("--overwrite", action='store_true',
                       help="If True, will enable to use an already existing save_dir.")
    group.add_argument("--lr", default=0.0001, type=float, help="Learning rate.")
    group.add_argument("--weight_decay", default=0.0, type=float, help="Optimizer weight decay.")
    #group.add_argument("--lr_anneal_steps", default=0, type=int, help="Number of learning rate anneal steps.")
    group.add_argument("--eval_batch_size", default=32, type=int,
                       help="Batch size during evaluation loop. Do not change this unless you know what you are doing. "
                            "T2m precision calculation is based on fixed batch size 32.")
    group.add_argument("--eval_split", default='test', choices=['val', 'test'], type=str,
                       help="Which split to evaluate on during training.")
    group.add_argument("--eval_during_training", action='store_true',
                       help="If True, will run evaluation during training.")
    group.add_argument("--eval_rep_times", default=3, type=int,
                       help="Number of repetitions for evaluation loop during training.")
    group.add_argument("--eval_num_samples", default=1_000, type=int,
                       help="If -1, will use all samples in the specified split.")
    group.add_argument("--log_interval", default=1_000, type=int,
                       help="Log losses each N steps")
    group.add_argument("--save_interval", default=10_000, type=int,
                       help="Save checkpoints and run evaluation each N steps")
    group.add_argument("--num_steps", default=600_000, type=int,
                       help="Training will stop after the specified number of steps.")
    group.add_argument("--resume_checkpoint", default="", type=str,
                       help="If not empty, will start from the specified checkpoint (path to model###.pt file).")


def add_semantic_regressor_training_options(parser):
    group = parser.add_argument_group('semantic_regressor_training')
    group.add_argument("--model_type", default='modiffae',
                       choices=['modiffae', 'semantic_regressor', 'semantic_generator'], type=str,
                       help="Different components of the system.")
    #base_dir, _ = os.path.split(os.path.dirname(get_model_path_from_args("modiffae")))
    #group.add_argument("--save_dir", default=os.path.join(base_dir, "semantic_regressor"), type=str,
    #                   help="Path to save checkpoints and results.")
    #group.add_argument("--save_dir", required=True, type=str,
    #                   help="Path to save checkpoints and results.")
    group.add_argument("--overwrite", action='store_true',
                       help="If True, will enable to use an already existing save_dir.")
    group.add_argument("--lr", default=0.005, type=float, help="Learning rate.")
    group.add_argument("--weight_decay", default=0.0, type=float, help="Optimizer weight decay.")
    #group.add_argument("--lr_anneal_steps", default=0, type=int, help="Number of learning rate anneal steps.")
    group.add_argument("--eval_batch_size", default=32, type=int,
                       help="Batch size during evaluation loop. Do not change this unless you know what you are doing. "
                            "T2m precision calculation is based on fixed batch size 32.")
    group.add_argument("--eval_split", default='test', choices=['val', 'test'], type=str,
                       help="Which split to evaluate on during training.")
    group.add_argument("--eval_during_training", action='store_true',
                       help="If True, will run evaluation during training.")
    group.add_argument("--eval_rep_times", default=3, type=int,
                       help="Number of repetitions for evaluation loop during training.")
    group.add_argument("--eval_num_samples", default=1_000, type=int,
                       help="If -1, will use all samples in the specified split.")
    group.add_argument("--log_interval", default=1_000, type=int,
                       help="Log losses each N steps")
    group.add_argument("--save_interval", default=10_000, type=int,
                       help="Save checkpoints and run evaluation each N steps")
    group.add_argument("--num_steps", default=600_000, type=int,
                       help="Training will stop after the specified number of steps.")
    group.add_argument("--resume_checkpoint", default="", type=str,
                       help="If not empty, will start from the specified checkpoint (path to model###.pt file).")


def add_sampling_options(parser):
    group = parser.add_argument_group('sampling')
    group.add_argument("--model_path", required=True, type=str,
                       help="Path to model####.pt file to be sampled.")
    group.add_argument("--output_dir", default='', type=str,
                       help="Path to results dir (auto created by the script). "
                            "If empty, will create dir in parallel to checkpoint.")
    group.add_argument("--num_samples", default=10, type=int,
                       help="Maximal number of prompts to sample, "
                            "if loading dataset from file, this field will be ignored.")
    group.add_argument("--num_repetitions", default=3, type=int,
                       help="Number of repetitions, per sample (text prompt/action)")
    #group.add_argument("--guidance_param", default=2.5, type=float,
    #                   help="For classifier-free sampling - specifies the s parameter, as defined in the paper.")


def add_model_path_option(parser, model_type):
    group = parser.add_argument_group(f'{model_type}_model_path')
    group.add_argument(f'--{model_type}_model_path', required=True, type=str,
                       help="Path to model####.pt file to be sampled.")


def add_save_dir_path(parser):
    group = parser.add_argument_group('save_directory')
    group.add_argument("--save_dir", required=True, type=str,
                       help="Path to save checkpoints and results.")

"""def add_generate_options(parser):
    group = parser.add_argument_group('generate')
    group.add_argument("--motion_length", default=6.0, type=float,
                       help="The length of the sampled motion [in seconds]. "
                            "Maximum is 9.8 for HumanML3D (text-to-motion), and 2.0 for HumanAct12 (action-to-motion)")
    group.add_argument("--input_text", default='', type=str,
                       help="Path to a text file lists text prompts to be synthesized. If empty, will take text prompts from dataset.")
    group.add_argument("--action_file", default='', type=str,
                       help="Path to a text file that lists names of actions to be synthesized. Names must be a subset of dataset/uestc/info/action_classes.txt if sampling from uestc, "
                            "or a subset of [warm_up,walk,run,jump,drink,lift_dumbbell,sit,eat,turn steering wheel,phone,boxing,throw] if sampling from humanact12. "
                            "If no file is specified, will take action names from dataset.")
    group.add_argument("--text_prompt", default='', type=str,
                       help="A text prompt to be generated. If empty, will take text prompts from dataset.")
    group.add_argument("--action_name", default='', type=str,
                       help="An action name to be generated. If empty, will take text prompts from dataset.")"""


"""def add_edit_options(parser):
    group = parser.add_argument_group('edit')
    group.add_argument("--edit_mode", default='in_between', choices=['in_between', 'upper_body'], type=str,
                       help="Defines which parts of the input motion will be edited.\n"
                            "(1) in_between - suffix and prefix motion taken from input motion, "
                            "middle motion is generated.\n"
                            "(2) upper_body - lower body joints taken from input motion, "
                            "upper body is generated.")
    group.add_argument("--text_condition", default='', type=str,
                       help="Editing will be conditioned on this text prompt. "
                            "If empty, will perform unconditioned editing.")
    group.add_argument("--prefix_end", default=0.25, type=float,
                       help="For in_between editing - Defines the end of input prefix (ratio from all frames).")
    group.add_argument("--suffix_start", default=0.75, type=float,
                       help="For in_between editing - Defines the start of input suffix (ratio from all frames).")"""


def add_evaluation_options(parser):
    group = parser.add_argument_group('eval')
    group.add_argument("--overwrite", action='store_true',
                       help="If True, will enable to use an already existing save_dir.")
    '''group.add_argument("--model_path", required=True, type=str,
                       help="Path to model####.pt file to be sampled.")
    group.add_argument("--eval_mode", default='wo_mm', choices=['wo_mm', 'mm_short', 'debug', 'full'], type=str,
                       help="wo_mm (t2m only) - 20 repetitions without multi-modality metric; "
                            "mm_short (t2m only) - 5 repetitions with multi-modality metric; "
                            "debug - short run, less accurate results."
                            "full (a2m only) - 20 repetitions.")
    group.add_argument("--guidance_param", default=2.5, type=float,
                       help="For classifier-free sampling - specifies the s parameter, as defined in the paper.")
'''


def add_generate_options(parser):
    group = parser.add_argument_group('generate')
    group.add_argument("--ratio", default=0.2, type=float, help="Percentage of synthetic data to generate.")
    #group.add_argument("--data_save_dir", default="./datasets/karate/",
    #                   type=str, help="Path to save checkpoints and results.")
    group.add_argument("--overwrite", action='store_true',
                       help="If True, will overwrite existing generated data.")

def modiffae_train_args():
    parser = ArgumentParser()
    add_base_options(parser)
    add_data_options(parser)
    add_diffusion_options(parser)
    add_modiffae_model_options(parser)
    add_modiffae_training_options(parser)
    return parser.parse_args()


def semantic_generator_train_args():
    parser = ArgumentParser()
    add_base_options(parser)
    add_data_options(parser)
    add_diffusion_options(parser)
    add_semantic_generator_model_options(parser)
    add_model_path_option(parser, model_type="modiffae")
    add_semantic_generator_training_options(parser)
    #add_sampling_options(parser)
    return parser.parse_args()


def semantic_regressor_train_args():
    parser = ArgumentParser()
    add_base_options(parser)
    add_data_options(parser)
    #add_diffusion_options(parser)
    add_semantic_regressor_model_options(parser)
    add_model_path_option(parser, model_type="modiffae")
    #add_sampling_options(parser)
    add_semantic_regressor_training_options(parser)
    #add_training_options(parser)
    return parser.parse_args()


"""def generation_args():
    parser = ArgumentParser()
    # args specified by the user: (all other will be loaded from the model)
    add_base_options(parser)
    add_sampling_options(parser)
    #add_generate_options(parser)
    return parser.parse_args()  # parse_and_load_from_model(parser, model_type="")"""


def generation_args():
    parser = ArgumentParser()
    add_base_options(parser)
    add_generate_options(parser)
    add_model_path_option(parser, model_type="modiffae")
    add_model_path_option(parser, model_type="semantic_generator")
    add_model_path_option(parser, model_type="semantic_regressor")
    return parser.parse_args()  # parse_and_load_from_model(parser, model_type="")


def editing_args():
    parser = ArgumentParser()
    # args specified by the user: (all other will be loaded from the model)
    add_base_options(parser)
    #add_sampling_options(parser)
    #add_edit_options(parser)
    return parser.parse_args()  #parse_and_load_from_model(parser)


def model_parser(model_type, model_path=None):
    parser = ArgumentParser()
    # args specified by the user: (all other will be loaded from the model)
    add_base_options(parser)
    #add_sampling_options(parser)
    #add_generate_options(parser)
    return parse_and_load_from_model(parser, model_type, model_path)

"""def modiffae_parser():
    parser = ArgumentParser()
    # args specified by the user: (all other will be loaded from the model)
    add_base_options(parser)
    #add_sampling_options(parser)
    #add_generate_options(parser)
    return parse_and_load_from_model(parser, model_type="modiffae")

def semantic_regressor_parser():
    parser = ArgumentParser()
    # args specified by the user: (all other will be loaded from the model)
    add_base_options(parser)
    #add_sampling_options(parser)
    #add_generate_options(parser)
    return parse_and_load_from_model(parser, model_type="latentnet")"""


# TODO: evaluation args for each of the three models
def evaluation_args():
    parser = ArgumentParser()
    # args specified by the user: (all other will be loaded from the model)
    add_base_options(parser)
    add_evaluation_options(parser)
    add_model_path_option(parser, model_type="modiffae")
    return parser.parse_args() #parse_and_load_from_model(parser)


def modiffae_validation_args():
    parser = ArgumentParser()
    # args specified by the user: (all other will be loaded from the model)
    add_base_options(parser)
    add_save_dir_path(parser)
    add_evaluation_options(parser)
    #add_model_path_option(parser, model_type="modiffae")
    return parser.parse_args()  # parse_and_load_from_model(parser)