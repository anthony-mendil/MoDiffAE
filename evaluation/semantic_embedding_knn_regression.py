from utils.fixseed import fixseed
import os
import numpy as np
import torch
from utils.parser_util import model_parser, modiffae_validation_args
from utils.model_util import create_modiffae_and_diffusion, load_model, calculate_embeddings
from utils import dist_util
from load.get_data import get_dataset_loader
import matplotlib.pyplot as plt
#from torchmetrics import F1Score
#from torcheval.metrics.functional import multiclass_f1_score
from sklearn.metrics import f1_score, balanced_accuracy_score, confusion_matrix
from collections import Counter
import seaborn as sns
from matplotlib.colors import ListedColormap
import colorcet as cc
import pandas as pd
import json

def determine_predictions_and_targets(train_embeddings, train_labels, validation_embedding, validation_label, k):
    distances_to_train_embeddings_list = list(np.linalg.norm(train_embeddings - validation_embedding, axis=1))
    train_labels_list = list(train_labels)

    distances_and_labels = list(zip(distances_to_train_embeddings_list, train_labels_list))
    distances_and_labels.sort(key=lambda x: x[0])

    k_closest = distances_and_labels[:k]
    k_closest_labels = np.array([e[1] for e in k_closest])

    k_closest_technique_labels = k_closest_labels[:, :5]
    k_closest_technique_labels_cls = [x for x in np.argmax(k_closest_technique_labels, axis=1)]

    technique_prediction = max(k_closest_technique_labels_cls, key=k_closest_technique_labels_cls.count)
    technique_target = np.argmax(validation_label[:5])

    #print(technique_prediction, technique_target)

    k_closest_average_label = np.mean(k_closest_labels, axis=0)
    #k_closest_average_label = np.expand_dims(k_closest_average_label, axis=1)

    #print(validation_label)

    grade_prediction = round(k_closest_average_label[5] * 12)
    grade_target_float = validation_label[5]
    grade_target = round(grade_target_float * 12)
    #print(grade_prediction, grade_target)
    #exit()

    #val_label = np.expand_dims(validation_label, axis=1)
    #technique_target = np.argmax(val_label[])

    #acc = k_closest_technique_labels_cls.count(val_label_cls) / len(k_closest_technique_labels_cls)

    #label_distance = np.linalg.norm(k_closest_average_label - val_label, axis=1)
    #skill_mae = label_distance[-1]

    #errors = [(val_label_cls, acc), skill_mae]

    #return errors
    return (technique_prediction, technique_target), (grade_prediction, grade_target)


def calc_distance_score(train_embeddings, train_labels, validation_embedding,
                        validation_label, grade_prio_probabilities, k):
    distances_to_train_embeddings_list = list(np.linalg.norm(train_embeddings - validation_embedding, axis=1))
    train_labels_list = list(train_labels)

    distances_and_labels = list(zip(distances_to_train_embeddings_list, train_labels_list))
    distances_and_labels.sort(key=lambda x: x[0])

    k_closest = distances_and_labels[:k]
    k_closest_labels = np.array([e[1] for e in k_closest])

    k_closest_technique_labels = k_closest_labels[:, :5]
    k_closest_technique_labels_cls = [x for x in np.argmax(k_closest_technique_labels, axis=1)]

    ####
    ##k_closest_grades = k_closest_labels[:, 5]
    #print(k_closest_grades)

    ##k_closest_grades_weights = [1 - grade_prio_probabilities[round(gr * 12)] for gr in k_closest_grades]
    #print(k_closest_grades_weights)

    ##k_closest_weighted_average_grade = np.average(k_closest_grades, weights=k_closest_grades_weights)
    #print(k_closest_weighted_average_grade)

    ##grade_prediction = round(k_closest_weighted_average_grade * 12)

    #exit()


    ####

    k_closest_average_label = np.mean(k_closest_labels, axis=0)
    k_closest_average_label = np.expand_dims(k_closest_average_label, axis=1)

    technique_prediction = max(k_closest_technique_labels_cls, key=k_closest_technique_labels_cls.count)

    # add the labels all together
    # multiply the result bt the class prio probability


    technique_target = np.argmax(validation_label[:5])

    val_label = np.expand_dims(validation_label, axis=1)
    #val_label_cls = np.argmax(val_label)

    #technique_acc = k_closest_technique_labels_cls.count(technique_target) / len(k_closest_technique_labels_cls)
    if technique_prediction == technique_target:
        technique_acc = 1
    else:
        technique_acc = 0




    #label_distance = np.linalg.norm(k_closest_average_label - val_label, axis=1)
    #grade_mae = label_distance[-1]
    grade_mae = np.linalg.norm(k_closest_average_label[5] - val_label[5])
    #grade_mae = label_distance[-1]
    #grade_target = validation_label[5]

    # TODO: calc weihted avera with prio probability of skill level


    grade_prediction = round(np.squeeze(k_closest_average_label[5]) * 12)
    grade_target_float = validation_label[5]
    grade_target = round(grade_target_float * 12)

    errors = [(technique_target, technique_acc), (grade_target, grade_mae)]
    #errors = [(technique_target, technique_acc), (grade_target, k_closest_weighted_average_grade)]

    predictions_and_targets = (
        (technique_prediction, technique_target),
        (grade_prediction, grade_target)
    )

    return errors, predictions_and_targets


def count_label_occurrences():
    pass


def calc_checkpoint_metrics(model_path):
    modiffae_args = model_parser(model_type="modiffae", model_path=model_path)

    train_data = get_dataset_loader(
        name=modiffae_args.dataset,
        batch_size=modiffae_args.batch_size,
        num_frames=modiffae_args.num_frames,
        test_participant=modiffae_args.test_participant,
        pose_rep=modiffae_args.pose_rep,
        split='train'
    )

    validation_data = get_dataset_loader(
        name=modiffae_args.dataset,
        batch_size=modiffae_args.batch_size,
        num_frames=modiffae_args.num_frames,
        test_participant=modiffae_args.test_participant,
        pose_rep=modiffae_args.pose_rep,
        split='validation'
    )

    model, diffusion = create_modiffae_and_diffusion(modiffae_args, train_data)

    print(f"Loading checkpoints from [{model_path}]...")
    state_dict = torch.load(model_path, map_location='cpu')
    load_model(model, state_dict)

    model.to(dist_util.dev())
    model.eval()

    train_semantic_embeddings, train_labels = calculate_embeddings(train_data, model.semantic_encoder,
                                                                   return_labels=True)
    train_semantic_embeddings = train_semantic_embeddings.cpu().detach().numpy()
    train_labels = train_labels.cpu().detach().numpy()

    grade_train_labels = list(train_labels[:, 5])
    grade_train_labels = [round(lab * 12) for lab in grade_train_labels]
    grade_prio_probabilities = {gr: cnt/len(grade_train_labels) for gr, cnt in Counter(grade_train_labels).items()}

    validation_semantic_embeddings, validation_labels = calculate_embeddings(validation_data, model.semantic_encoder,
                                                                             return_labels=True)
    validation_semantic_embeddings = validation_semantic_embeddings.cpu().detach().numpy()
    validation_labels = validation_labels.cpu().detach().numpy()

    technique_predictions = []
    technique_targets = []
    grade_predictions = []
    grade_targets = []

    error_scores = []
    for i in range(validation_semantic_embeddings.shape[0]):
        val_embedding = validation_semantic_embeddings[i]
        val_label = validation_labels[i]
        error_score, predictions_and_targets = (
            calc_distance_score(train_semantic_embeddings, train_labels,
                                val_embedding, val_label, grade_prio_probabilities, k=15)) # 50 15 is good
        error_scores.append(error_score)

        technique_predictions.append(predictions_and_targets[0][0])
        technique_targets.append(predictions_and_targets[0][1])
        grade_predictions.append(predictions_and_targets[1][0])
        grade_targets.append(predictions_and_targets[1][1])

    predictions_and_targets_combined = (
        (technique_predictions, technique_targets),
        (grade_predictions, grade_targets)
    )

    technique_accuracies = []
    for cls in range(5):
        tech_scores = [ac for (c, ac), _ in error_scores if c == cls]
        tech_scores_avg = np.mean(tech_scores)
        technique_accuracies.append(tech_scores_avg)

    grade_maes = []
    for gr in range(13):
        grade_scores = [mae for _, (g, mae) in error_scores if g == gr]
        grade_scores_avg = np.mean(grade_scores)
        grade_maes.append(grade_scores_avg)
    #grade_mae = np.mean([err for _, err in error_scores])

    #metrics = np.append(technique_accuracies, grade_maes)
    #return metrics
    return technique_accuracies, grade_maes, predictions_and_targets_combined

'''def calc_checkpoint_metrics(model_path):
    modiffae_args = model_parser(model_type="modiffae", model_path=model_path)

    train_data = get_dataset_loader(
        name=modiffae_args.dataset,
        batch_size=modiffae_args.batch_size,
        num_frames=modiffae_args.num_frames,
        test_participant=modiffae_args.test_participant,
        pose_rep=modiffae_args.pose_rep,
        split='train'
    )

    validation_data = get_dataset_loader(
        name=modiffae_args.dataset,
        batch_size=modiffae_args.batch_size,
        num_frames=modiffae_args.num_frames,
        test_participant=modiffae_args.test_participant,
        pose_rep=modiffae_args.pose_rep,
        split='validation'
    )

    model, diffusion = create_modiffae_and_diffusion(modiffae_args, train_data)

    print(f"Loading checkpoints from [{model_path}]...")
    state_dict = torch.load(model_path, map_location='cpu')
    load_model(model, state_dict)

    model.to(dist_util.dev())
    model.eval()

    train_semantic_embeddings, train_labels = calculate_embeddings(train_data, model.semantic_encoder,
                                                                   return_labels=True)
    train_semantic_embeddings = train_semantic_embeddings.cpu().detach().numpy()
    train_labels = train_labels.cpu().detach().numpy()

    validation_semantic_embeddings, validation_labels = calculate_embeddings(validation_data, model.semantic_encoder,
                                                                             return_labels=True)
    validation_semantic_embeddings = validation_semantic_embeddings.cpu().detach().numpy()
    validation_labels = validation_labels.cpu().detach().numpy()

    #error_scores = []
    technique_predictions = []
    technique_targets = []
    grade_predictions = []
    grade_targets = []

    for i in range(validation_semantic_embeddings.shape[0]):
        val_embedding = validation_semantic_embeddings[i]
        val_label = validation_labels[i]
        t, g = determine_predictions_and_targets(
            train_semantic_embeddings, train_labels, val_embedding, val_label, k=50) # 50
        technique_predictions.append(t[0])
        technique_targets.append(t[1])
        grade_predictions.append(g[0])
        grade_targets.append(g[1])
        #error_scores.append(error_score)

    technique_f1_score = f1_score(technique_targets, technique_predictions, average='macro')
    grade_f1_score = f1_score(grade_targets, grade_predictions, average='macro')
    avg_f1_score = (technique_f1_score + grade_f1_score) / 2

    #technique_f1_score = balanced_accuracy_score(technique_targets, technique_predictions)
    #grade_f1_score = balanced_accuracy_score(grade_targets, grade_predictions)
    #avg_f1_score = (technique_f1_score + grade_f1_score) / 2

    return technique_f1_score, grade_f1_score, avg_f1_score

    #print(technique_f1_score, grade_f1_score)
    #exit()'''

'''technique_accuracies = []
for cls in range(5):
    tech_scores = [ac for (c, ac), _ in error_scores if c == cls]
    tech_scores_avg = np.mean(tech_scores)
    technique_accuracies.append(tech_scores_avg)

skill_mae = np.mean([err for _, err in error_scores])

metrics = np.append(technique_accuracies, skill_mae)
return metrics'''




def main():
    args = modiffae_validation_args()
    fixseed(args.seed)
    dist_util.setup_dist(args.device)

    checkpoints = [p for p in sorted(os.listdir(args.save_dir)) if p.startswith('model') and p.endswith('.pt')]

    #checkpoint_metrics = []

    technique_accuracies_all = []
    grade_maes_all = []
    predictions_and_targets_all = []
    for ch in checkpoints:
        model_path = os.path.join(args.save_dir, ch)
        #checkpoint_metric = calc_checkpoint_metrics(model_path)
        technique_accuracies, grade_maes, predictions_and_targets_combined = calc_checkpoint_metrics(model_path)
        technique_accuracies_all.append(technique_accuracies)
        grade_maes_all.append(grade_maes)
        predictions_and_targets_all.append(predictions_and_targets_combined)
        #print(technique_accuracies, grade_maes, predictions_and_targets_combined)
        #exit()
        #checkpoint_metrics.append(checkpoint_metric)

    #checkpoint_metrics = np.array(checkpoint_metrics)
    technique_accuracies_all = np.array(technique_accuracies_all)
    grade_maes_all = np.array(grade_maes_all)
    #predictions_and_targets_all = np.array(predictions_and_targets_all)

    checkpoints = [str(int(int(ch.strip("model").strip(".pt")) / 1000)) + "k" for ch in checkpoints]

    technique_idx_to_name = {
        0: "ACC: Reverse punch",
        1: "ACC: Front kick",
        2: "ACC: Low roundhouse kick",
        3: "ACC: High roundhouse kick",
        4: "ACC: Spinning back kick"
    }

    technique_idx_to_name_short = {
        0: "RP",
        1: "FK",
        2: "LRK",
        3: "HRK",
        4: "SBK"
    }

    grade_idx_to_name = {
        0: 'MAE: 9 kyu',
        1: 'MAE: 8 kyu',
        2: 'MAE: 7 kyu',
        3: 'MAE: 6 kyu',
        4: 'MAE: 5 kyu',
        5: 'MAE: 4 kyu',
        6: 'MAE: 3 kyu',
        7: 'MAE: 2 kyu',
        8: 'MAE: 1 kyu',
        9: 'MAE: 1 dan',
        10: 'MAE: 2 dan',
        11: 'MAE: 3 dan',
        12: 'MAE: 4 dan'
    }

    grade_idx_to_name_short = {
        0: '9 kyu',
        1: '8 kyu',
        2: '7 kyu',
        3: '6 kyu',
        4: '5 kyu',
        5: '4 kyu',
        6: '3 kyu',
        7: '2 kyu',
        8: '1 kyu',
        9: '1 dan',
        10: '2 dan',
        11: '3 dan',
        12: '4 dan'
    }

    f = plt.figure()
    f.set_figwidth(15)
    f.set_figheight(8)

    #checkpoint_metrics_technique = checkpoint_metrics[:5, :]
    #checkpoint_metrics_grade = checkpoint_metrics[5:]

    x = checkpoints
    for idx in range(technique_accuracies_all.shape[1]):
        y = technique_accuracies_all[:, idx]
        plt.plot(x, y, label=f"{technique_idx_to_name[idx]}")

    technique_unweighted_average_recalls = []
    for idx in range(technique_accuracies_all.shape[0]):
        technique_unweighted_average_recalls.append(np.mean(technique_accuracies_all[idx, :]))
    best_technique_avg_idx = np.argmax(technique_unweighted_average_recalls)
    print(best_technique_avg_idx)

    plt.plot(x, technique_unweighted_average_recalls, label=f"UAR", color='black')

    plt.vlines(x=[best_technique_avg_idx], ymin=0, ymax=1, colors='black', ls='--', lw=2,
               label='Best UAR')

    # TODO: store metrics of best ie chosen ckpt in json, store all plots including confusion matrices for the best
    #   adjust legend position and number and letter size according to how it looks in thesis

    # TODO: for regressor its the same code, only add model loading for regressor and use it for classification
    #   instead of knn

    plt.legend()

    eval_dir = os.path.join(args.save_dir, "evaluation")
    if not os.path.exists(eval_dir):
        os.makedirs(eval_dir)

    fig_save_path = os.path.join(eval_dir, "knn_technique_uar")
    plt.savefig(fig_save_path)

    plt.clf()

    #my_cmap = ListedColormap(sns.color_palette("Spectral", 14))
    #plt.rcParams["axes.prop_cycle"] = plt.cycler("color", my_cmap)
    #plt.rcParams["axes.prop_cycle"] = plt.cycler("color", plt.cm.tab20c.colors)

    #with sns.color_palette("Paired", n_colors=14):
    with sns.color_palette(cc.glasbey, n_colors=14):
        for idx in range(grade_maes_all.shape[1]):
            y = grade_maes_all[:, idx]
            plt.plot(x, y, label=f"{grade_idx_to_name[idx]}")

    grade_averages = []
    for idx in range(grade_maes_all.shape[0]):
        grade_averages.append(np.mean(grade_maes_all[idx, :]))
    best_grade_avg_idx = np.argmin(grade_averages)
    print(best_grade_avg_idx)

    plt.plot(x, grade_averages, label=f"UMAE", color='black')

    plt.vlines(x=[best_grade_avg_idx], ymin=0, ymax=1, colors='black', ls='--', lw=2,
               label='Best UMAE')

    plt.legend()

    #plt.show()

    fig_save_path = os.path.join(eval_dir, "knn_grade_umae")
    plt.savefig(fig_save_path)

    plt.clf()

    f = plt.figure()
    f.set_figwidth(15)
    f.set_figheight(8)

    grade_averages_acc = [1 - avg for avg in grade_averages]
    combined_metric = (np.array(grade_averages_acc) + np.array(technique_unweighted_average_recalls)) / 2
    best_combined_avg_idx = np.argmax(combined_metric)
    print(best_combined_avg_idx)

    plt.plot(x, technique_unweighted_average_recalls, label=f"UAR")
    plt.plot(x, grade_averages, label=f"UMAE")
    plt.plot(x, combined_metric, label=f"Combined score", color='black')

    plt.vlines(x=[best_combined_avg_idx], ymin=0, ymax=1, colors='black', ls='--', lw=2,
               label='Best combined score')

    plt.legend()
    #plt.show()

    fig_save_path = os.path.join(eval_dir, "knn_combined")
    plt.savefig(fig_save_path)

    # TODO: plot confusion matrics and own metric averga ebtween grade and tchnique


    chosen_model_predictions_and_targets = predictions_and_targets_all[best_combined_avg_idx][0]
    print(chosen_model_predictions_and_targets)

    technique_confusion_matrix_values = confusion_matrix(
        chosen_model_predictions_and_targets[1], chosen_model_predictions_and_targets[0]
    )

    print(technique_confusion_matrix_values)

    df_cm = pd.DataFrame(technique_confusion_matrix_values,
                         index=[technique_idx_to_name_short[i] for i in technique_idx_to_name_short.keys()],
                         columns=[technique_idx_to_name_short[i] for i in technique_idx_to_name_short.keys()])

    plt.figure(figsize=(10, 7))
    s = sns.heatmap(df_cm, annot=True, cmap='Blues')
    s.set_xlabel('Predicted technique')#, fontsize=10)
    s.set_ylabel('True technique')#, fontsize=10)
    #plt.show()

    fig_save_path = os.path.join(eval_dir, "best_combined_technique_confusion_matrix")
    plt.savefig(fig_save_path)
    #####

    chosen_model_predictions_and_targets = predictions_and_targets_all[best_combined_avg_idx][1]
    print(chosen_model_predictions_and_targets)

    grade_confusion_matrix_values = confusion_matrix(
        chosen_model_predictions_and_targets[1], chosen_model_predictions_and_targets[0]
    )

    print(grade_confusion_matrix_values)

    df_cm = pd.DataFrame(grade_confusion_matrix_values,
                         index=[grade_idx_to_name_short[i] for i in grade_idx_to_name_short.keys()],
                         columns=[grade_idx_to_name_short[i] for i in grade_idx_to_name_short.keys()])

    plt.figure(figsize=(10, 7))
    s = sns.heatmap(df_cm, annot=True, cmap='Blues')
    s.set_xlabel('Predicted grade')  # , fontsize=10)
    s.set_ylabel('True grade')  # , fontsize=10)
    #plt.show()
    fig_save_path = os.path.join(eval_dir, "best_combined_grade_confusion_matrix")
    plt.savefig(fig_save_path)

    best_results = {
        "best technique checkpoint": str(checkpoints[best_technique_avg_idx]),
        "UAR of best technique checkpoint": str(technique_unweighted_average_recalls[best_technique_avg_idx]),
        "best grade checkpoint": str(checkpoints[best_grade_avg_idx]),
        "UMAE of best grade checkpoint": str(grade_averages[best_grade_avg_idx]),
        "best combined checkpoint": str(checkpoints[best_combined_avg_idx]),
        "UAR of best combined checkpoint": str(technique_unweighted_average_recalls[best_combined_avg_idx]),
        "UMAE of best combined checkpoint": str(grade_averages[best_combined_avg_idx]),
        "Overall score of best combined checkpoint": str(combined_metric[best_combined_avg_idx])
    }

    print(best_results)

    best_results_save_path = os.path.join(eval_dir, "best_results_overview.json")
    with open(best_results_save_path, 'w') as outfile:
        json.dump(best_results, outfile)


if __name__ == "__main__":
    main()
