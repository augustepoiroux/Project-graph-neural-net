import sys
import argparse
import json
import os

import torch
from models import get_model
from loaders.data_generator import Generator
from loaders.siamese_loaders import siamese_loader
import trainer as trainer
from toolbox import logger, metrics
from toolbox.losses import get_criterion

def parse_args():
    parser = argparse.ArgumentParser(description='')
    parser.add_argument('--name', type=str, default ='GNN-Reg')
    parser.add_argument('--model-path', type=str,
                        help='path to pretrained model')   
    parser.add_argument('--num_examples_test', type=int, default=1000)
    parser.add_argument('--generative_model', type=str, default='Regular')
    parser.add_argument('--noise_model', type=str, default='ErdosRenyi')
    parser.add_argument('--edge_density', type=float, default=0.2)
    parser.add_argument('--n_vertices', type=int, default = 50)
    parser.add_argument('--vertex_proba', type=float, default=1.)
    parser.add_argument('--noise',type=float, default=0.15)
    args = parser.parse_args()
    argparse_dict = vars(args)
    return argparse_dict


def load_model(model, filename):
    if os.path.exists(filename):
        checkpoint = torch.load(filename)
        model.load_state_dict(checkpoint['state_dict'])
        return model
    else:
        print('model does not exist!')
        return None



def main():
    global args
    args = parse_args()
    
    #print(args)
    config_file = os.path.join(args['model_path'],'config.json')
    with open(config_file) as json_file:
        config_model = json.load(json_file)
    
    #print(config_model['arch'])
    #print(config_model)
    args['path_dataset'] = config_model['path_dataset']
    use_cuda = not config_model['cpu'] and torch.cuda.is_available()
    device = 'cuda' if use_cuda else 'cpu'
    print('Using device:', device)

    model = get_model(config_model['arch'])
    model.to(device)
    model_file = os.path.join(args['model_path'],'model_best.pth.tar')
    print(model_file)
    model = load_model(model, model_file)
    
    criterion = get_criterion(device, config_model['train']['loss_reduction'])
    exp_logger = logger.Experiment(args['name'])
    exp_logger.add_meters('test', metrics.make_meter_matching())

    gene_test = Generator('test', args)
    gene_test.load_dataset()
    test_loader = siamese_loader(gene_test, config_model['train']['batch_size'], gene_test.constant_n_vertices)
    acc, loss = trainer.val_triplet(test_loader,model,criterion,exp_logger,device,epoch=0,eval_score=metrics.accuracy_linear_assignment,val_test='test')
    

if __name__ == '__main__':
    main()