import os
import random
import itertools
import networkx
import torch
import torch.utils
from toolbox import utils
import numpy as np

GENERATOR_FUNCTIONS = {}

def generates(name):
    """ Register a generator function for a graph distribution """
    def decorator(func):
        GENERATOR_FUNCTIONS[name] = func
        return func
    return decorator

@generates("ErdosRenyi")
def generate_erdos_renyi_netx(p, N):
    """ Generate random Erdos Renyi graph """
    g = networkx.erdos_renyi_graph(N, p)
    W = networkx.adjacency_matrix(g).todense()
    return g, torch.as_tensor(W, dtype=torch.float)

@generates("BarabasiAlbert")
def generate_barabasi_albert_netx(p, N):
    """ Generate random Barabasi Albert graph """
    m = int(p*(N -1)/2)
    g = networkx.barabasi_albert_graph(N, m)
    W = networkx.adjacency_matrix(g).todense()
    return g, torch.as_tensor(W, dtype=torch.float)

@generates("Regular")
def generate_regular_graph_netx(p, N):
    """ Generate random regular graph """
    d = p * N
    d = int(d)
    # Make sure N * d is even
    if N * d % 2 == 1:
        d += 1
    g = networkx.random_regular_graph(d, N)
    W = networkx.adjacency_matrix(g).todense()
    return g, torch.as_tensor(W, dtype=torch.float)

def adjacency_matrix_to_tensor_representation(W):
    """ Create a tensor B[:,:,1] = W and B[i,i,0] = deg(i)"""
    degrees = W.sum(1)
    B = torch.zeros((len(W), len(W), 2))
    B[:, :, 1] = W
    indices = torch.arange(len(W))
    B[indices, indices, 0] = degrees
    return B

MERGE_FUNCTIONS = {}

def merge_graphs(name):
    """ Register a merge function for a graph distribution """
    def decorator(func):
        MERGE_FUNCTIONS[name] = func
        return func
    return decorator

@merge_graphs("ErdosRenyi")
def merge_erdos_renyi(p, W_1, W_2):
    """ Merge 2 random Erdos Renyi graph represented by their adjacency matrix"""

    #W1 and W2 are tensor
    n_1 = W_1.shape[0]
    n_2 = W_2.shape[0]
    W_new = torch.zeros(n_1+n_2, n_1+n_2)
    perm = np.random.permutation(n_1+n_2) #choose a random order for the nodes in the new graph
    labels = torch.zeros(n_1+n_2, 1)

    #copy the edges of g_1
    for i in range(n_1): #nodes of g_1
        for j in range(n_1): #nodes of g_1
            W_new[perm[i]][perm[j]] = W_1[i][j]

    #copy the edges of g_2
    for i in range(n_2): #nodes of g_2
        labels[perm[i+n_1]][0] = 1
        for j in range(n_2): #nodes of g_2
            W_new[perm[i+n_1]][perm[j+n_1]] = W_1[i][j]

    #build connections between the 2 graphs
    for i in range(n_1): #nodes of g_1
        for j in range(n_1, n_1+n_2): #nodes of g_2
            r = random.random()
            if r<p:
                W_new[perm[i]][perm[j]] = 1.
                W_new[perm[j]][perm[i]] = 1.

    return W_new, labels

@merge_graphs("BarabasiAlbert")
def merge_barabasi_albert_netx(p, B_1, B_2):
    """ Merge random Barabasi Albert graphs """
    raise ValueError('Generative model {} not supported'
                             .format(self.generative_model))

@merge_graphs("Regular")
def generate_regular_graph_netx(p, B_1, B_2):
    """ Merge random regular graph """
    raise ValueError('Generative model {} not supported'
                             .format(self.generative_model))


class Base_Generator(torch.utils.data.Dataset):
    def __init__(self, name, path_dataset, num_examples):
        self.path_dataset = path_dataset
        self.name = name
        self.num_examples = num_examples

    def load_dataset(self):
        """
        Look for required dataset in files and create it if
        it does not exist
        """
        filename = self.name + '.pkl'
        path = os.path.join(self.path_dataset, filename)
        if os.path.exists(path):
            print('Reading dataset at {}'.format(path))
            data = torch.load(path)
            self.data = list(data)
        else:
            print('Creating dataset.')
            self.data = []
            self.create_dataset()
            print('Saving datatset at {}'.format(path))
            torch.save(self.data, path)
    
    def create_dataset(self):
        for _ in range(self.num_examples):
            example = self.compute_example()
            self.data.append(example)

    def __getitem__(self, i):
        """ Fetch sample at index i """
        return self.data[i]

    def __len__(self):
        """ Get dataset length """
        return len(self.data)


class Generator(Base_Generator):
    """
    Build a numpy dataset of pairs of (Graph, noisy Graph)
    """
    def __init__(self, name, args):
        num_examples = args['num_examples_' + name]

        self.g_1_generative_model = args['graph_1']['generative_model']
        self.g_1_edge_density = args['graph_1']['edge_density']
        n_vertices_1 = args['graph_1']['n_vertices']
        vertex_proba_1 = args['graph_1']['vertex_proba']

        self.g_2_generative_model = args['graph_2']['generative_model']
        self.g_2_edge_density = args['graph_2']['edge_density']
        n_vertices_2 = args['graph_2']['n_vertices']
        vertex_proba_2 = args['graph_2']['vertex_proba']

        self.merge_generative_model = args['merge_arg']['generative_model']
        self.merge_edge_density = args['merge_arg']['edge_density']

        subfolder_name = 'labels_{}_{}_{}_{}_{}_{}'.format(num_examples,
                                                     self.g_1_generative_model, self.g_1_edge_density,
                                                     self.g_2_generative_model, self.g_2_edge_density,
                                                     self.merge_edge_density)
        path_dataset = os.path.join(args['path_dataset'],
                                         subfolder_name)
        super().__init__(name, path_dataset, num_examples)
        self.data = []
        self.constant_n_vertices = (vertex_proba_1==1.) and (vertex_proba_2==1.)
        self.n_vertices_sampler_1 = torch.distributions.Binomial(n_vertices_1, vertex_proba_1)
        self.n_vertices_sampler_2 = torch.distributions.Binomial(n_vertices_2, vertex_proba_2)
        
        
        utils.check_dir(self.path_dataset)

    def compute_example(self):
        """
        Compute pairs (Adjacency, labels of nodes)
        """
        n_vertices_1 = int(self.n_vertices_sampler_1.sample().item())
        n_vertices_2 = int(self.n_vertices_sampler_2.sample().item())
        try:
            g_1, W_1 = GENERATOR_FUNCTIONS[self.g_1_generative_model](self.g_1_edge_density, n_vertices_1)
        except KeyError:
            raise ValueError('Generative model {} not supported'
                             .format(self.g_1_generative_model))
        try:
            g_2, W_2 = GENERATOR_FUNCTIONS[self.g_2_generative_model](self.g_2_edge_density, n_vertices_2)
        except KeyError:
            raise ValueError('Generative model {} not supported'
                             .format(self.g_2_generative_model))

        W_new, labels = MERGE_FUNCTIONS[self.merge_generative_model](self.merge_edge_density, W_1, W_2)
        B_new = adjacency_matrix_to_tensor_representation(W_new) ###
        return B_new, labels