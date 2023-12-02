import numpy as np
import os
from load.dataset import Dataset
import utils.karate.data_info as data_info
import torch

class KaratePoses(Dataset):
    def __init__(self, test_participant, data_path="datasets/karate", split="train",
                 pose_rep="xyz", num_joints=39, root_joint_name='T10', **kwargs):
                #pose_rep="rot_6d", num_joints=39, root_joint_name='T10', **kwargs):

        root_joint_idx = data_info.joint_to_index[root_joint_name]
        super().__init__(pose_rep=pose_rep, num_joints=num_joints, root_joint_idx=root_joint_idx, **kwargs)

        self.data_path = data_path

        self.data_name = "karate"
        self.xyz_reconstruction_mode = "geometry"

        #if split is not None:
        data_file_path = os.path.join(data_path, f'leave_{test_participant}_out', f'{split}.npy')
        #else:
        #    data_file_path = os.path.join(data_path, 'karate_motion_modified.npy')

        data = np.load(data_file_path, allow_pickle=True)

        #data = np.where(data['condition'] == 'air', data)
        #data = data[data['condition'] == 'air']

        #print(len(data))
        #exit()

        #print(pose_rep)

        self._pose = [x for x in data["joint_axis_angles"]]
        self._num_frames_in_video = [p.shape[0] for p in self._pose]

        self._joints = [x for x in data["joint_positions"]]

        self._actions = [x for x in data["technique_cls"]]

        self._joint_distances = [x for x in data["joint_distances"]]

        num_of_grades = len(karate_grade_enumerator.keys())
        grade_to_label = lambda grade: (1 / (num_of_grades - 1)) * karate_grade_enumerator[grade]
        self._grades = [grade_to_label(x) for x in data['grade']]
        #self._grades = [karate_grade_enumerator[x] for x in data['grade']]
        #self._grades = [np.array([1.0, 0.0]) if grade_to_label(x) > 0.5 else np.array([0.0, 1.0]) for x in data['grade']]

        total_num_actions = 5
        self.num_actions = total_num_actions

        self.num_of_attributes = 6

        self._train = list(range(len(self._pose)))

        keep_actions = np.arange(0, total_num_actions)

        self._action_to_label = {x: i for i, x in enumerate(keep_actions)}
        self._label_to_action = {i: x for i, x in enumerate(keep_actions)}

        self._action_classes = karate_action_enumerator

    def _load_joints(self, ind, frame_ix):
        return self._joints[ind][frame_ix].reshape(-1, 39, 3)

    def _load_rot_vec(self, ind, frame_ix):
        pose = self._pose[ind][frame_ix].reshape(-1, 38, 3)
        return pose

    def _load_labels(self, ind):
        skill_labels = np.array([[self._grades[ind]]])
        #one_hot_skill_labels = np.eye(len(karate_grade_enumerator))[skill_labels]
        labels = np.array([self._actions[ind]])
        one_hot_labels = np.eye(len(karate_action_enumerator))[labels]

        #one_hot_labels = np.append(one_hot_labels, one_hot_skill_labels, axis=1)
        one_hot_labels = np.append(one_hot_labels, skill_labels, axis=1)

        #print(ind)
        #print(one_hot_labels)
        #exit()
        return one_hot_labels

    def get_grades(self):
        return self._grades

    def get_joint_distances(self):
        return self._joint_distances


"""class KarateEmbeddings(torch.utils.data.Dataset):
    def __init__(self, emb, att):
        self.emb = emb
        self.att = att
        if len(self.emb) != len(self.att):
            raise Exception("The length of the embeddings does not match the length of the attributes")

    def __len__(self):
        return len(self.emb)

    def __getitem__(self, index):
        e = self.emb[index]
        a = self.att[index]
        return e, a"""


karate_grade_enumerator = {
    '9 kyu': 0,
    '8 kyu': 1,
    '7 kyu': 2,
    '6 kyu': 3,
    '5 kyu': 4,
    '4 kyu': 5,
    '3 kyu': 6,
    '2 kyu': 7,
    '1 kyu': 8,
    '1 dan': 9,
    '2 dan': 10,
    '3 dan': 11,
    '4 dan': 12
}

karate_action_enumerator = {
    0: 'Gyaku-Zuki',
    1: 'Mae-Geri',
    2: 'Mawashi-Geri gedan',
    3: 'Mawashi-Geri jodan',
    4: 'Ushiro-Mawashi-Geri'
}
