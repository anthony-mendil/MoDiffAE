import os
import sys
import json
import torch
from utils.fixseed import fixseed
from utils.parser_util import classify_args, train_args
from utils import dist_util
from training.modiffae_training_loop import ModiffaeTrainLoop
from training.semantic_regressor_training_loop import SemanticRegressorTrainLoop
from load.get_data import get_dataset_loader
from model.semantic_regressor import SemanticRegressor
from utils.model_util import create_model_and_diffusion, load_model, calculate_z_parameters
from training.train_platforms import TensorboardPlatform


def main():
    args = None
    try:
        model_type = sys.argv[sys.argv.index('--model_type') + 1]
    except ValueError:
        raise Exception('No model_type specified. Options: modiffae, semantic_regressor, semantic_ddim')

    if model_type == "modiffae":
        args = train_args()
        args.save_dir = os.path.join(args.save_dir, "modiffae")
    elif model_type == "semantic_regressor":
        args = classify_args()
        args.save_dir = os.path.join(args.save_dir, "semantic_regressor")
    elif model_type == "semantic_ddim":
        pass
        #args.save_dir = os.path.join(args.save_dir, "semantic_ddim")
    else:
        pass

    fixseed(args.seed)

    train_platform = TensorboardPlatform(args.save_dir)
    train_platform.report_args(args, name='Args')

    if args.save_dir is None:
        raise FileNotFoundError('save_dir was not specified.')
    elif os.path.exists(args.save_dir) and not args.overwrite:
        raise FileExistsError('save_dir [{}] already exists.'.format(args.save_dir))
    elif not os.path.exists(args.save_dir):
        os.makedirs(args.save_dir)
    args_path = os.path.join(args.save_dir, 'args.json')
    with open(args_path, 'w') as fw:
        json.dump(vars(args), fw, indent=4, sort_keys=True)

    dist_util.setup_dist(args.device)

    print("creating train data loader...")
    train_data = get_dataset_loader(
        name=args.dataset,
        batch_size=args.batch_size,
        num_frames=args.num_frames,
        test_participant='b0372',
        split='train'
    )

    if args.dataset == "karate":
        print("creating validation data loader...")
        validation_data = get_dataset_loader(
            name=args.dataset,
            batch_size=args.batch_size,
            num_frames=args.num_frames,
            test_participant='b0372',
            split='validation'
        )
    else:
        validation_data = None

    print("creating model and diffusion...")
    model, diffusion = create_model_and_diffusion(args, train_data)

    if model_type == "modiffae":
        model.to(dist_util.dev())
        model.rot2xyz.smpl_model.eval()
        print('Total params: %.2fM' % (sum(p.numel() for p in model.parameters()) / 1000000.0))
        print("Training...")
        ModiffaeTrainLoop(args, train_platform, model, diffusion, train_data, validation_data).run_loop()
    elif model_type == "semantic_regressor":
        print(f"Loading checkpoints from [{args.model_path}]...")
        state_dict = torch.load(args.model_path, map_location='cpu')
        load_model(model, state_dict)

        semantic_encoder = model.semantic_encoder
        semantic_encoder.to(dist_util.dev())
        semantic_encoder.requires_grad_(False)
        semantic_encoder.eval()

        cond_mean, cond_std = calculate_z_parameters(train_data, semantic_encoder)

        sem_regressor = SemanticRegressor(
            input_dim=512,
            output_dim=6, #18,
            semantic_encoder=semantic_encoder,
            cond_mean=cond_mean,
            cond_std=cond_std
        )
        sem_regressor.to(dist_util.dev())
        SemanticRegressorTrainLoop(args, train_platform, sem_regressor, train_data, validation_data).run_loop()
    elif model_type == "semantic_ddim":
        pass
    else:
        pass

    train_platform.close()


if __name__ == "__main__":
    main()
