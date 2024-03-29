import numpy as np
import random
import time
import os
import logging
import models
import copy
from utils.config import load_model_config

import torch.nn.functional as F
import torch

import torch.nn.parallel
import torch.backends.cudnn as cudnn

import environment as envir

# Set up logger
logging.basicConfig(
    format='%(asctime)s:%(levelname)s:%(message)s',
    level=logging.INFO
)

"""
Contains the definition of the agent that will run in an
environment.
"""




class DQAgent:


		# We added n_edges_max.
    def __init__(self,model,lr,bs,n_step,env_name,node_max,n_edges_max):

        self.graphs = None
        self.embed_dim = 64
        self.model_name = model
        self.node_max = node_max
        self.alpha = 0.1
        self.gamma = 1 #0.99

        self.lambd = 0.
        self.n_step=n_step

        self.epsilon_=1
        self.epsilon_min=0.05
        self.discount_factor =0.999990
        
        self.memory = []
        self.memory_n=[]
        self.minibatch_length = bs

        self.n_edges_max = n_edges_max

        self.env=envir.Environment(env_name, n_edges_max) # We added n_edges_max
        self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        

        if self.model_name == 'S2V_QN_1':

            args_init = load_model_config()[self.model_name]
            self.model = models.S2V_QN_1(**args_init)
            #self.old_model = models.S2V_QN_1(**args_init)

        elif self.model_name == 'S2V_QN_2':
            args_init = load_model_config()[self.model_name]
            self.model = models.S2V_QN_2(**args_init)


        elif self.model_name== 'GCN_QN_1':

            args_init = load_model_config()[self.model_name]
            self.model = models.GCN_QN_1(**args_init)

        elif self.model_name == 'LINE_QN':

            args_init = load_model_config()[self.model_name]
            self.model = models.LINE_QN(**args_init)

        elif self.model_name == 'W2V_QN':

            args_init = load_model_config()[self.model_name]
            self.model = models.W2V_QN(G=self.graphs[self.games], **args_init)

        self.T = 5
        if torch.cuda.device_count() >= 1:
            print("Using", torch.cuda.device_count(), "GPUs!")
            self.model.to(self.device)
            #self.old_model.to(self.device)
            torch.backends.cudnn.benchmark = True
            
        else: print("Using CPU")

        self.criterion = torch.nn.MSELoss(reduction='sum').to(self.device)
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
        if torch.cuda.device_count() > 1: 
            self.model = torch.nn.DataParallel(self.model)
            #self.old_model = torch.nn.DataParallel(self.old_model)


    """
    p : embedding dimension
       
    """
    def reset(self, g):
        self.games = g
        self.env.reset(g)
        if (len(self.memory_n) != 0) and (len(self.memory_n) % 500000 == 0): #once memory comes to 500000, cut it down to 300000. Better if we make sure the RECENT datas to be preserved.
            tmp_mem = self.memory_n[-300000:].copy()
            self.memory_n.clear()
            self.memory_n=tmp_mem
            #random.sample(self.memory_n,300000)  random sample is not great

        self.nodes = self.graphs[self.games].nodes_count()
        self.last_action = 0
        self.last_reward = 0.0
        self.last_done = 0
        self.action = 0
        self.observation = torch.zeros(self.nodes, dtype=torch.int)
        self.reward = 0.0
        self.done = 0
        self.iter = 0
        self.memory.clear()
        self.zpad=np.zeros([2,self.nodes])
        """
        if (g+1)%200==0:
            self.old_model.load_state_dict(self.model.state_dict())
        """
        #you can use the auxiliary temp memory of the game and reset it here.
    def permutation_array(self, permu=None):
        if permu is None:
            permu=self.permu
            nodes_num=self.nodes
        else:
            nodes_num=permu[0].size
        
        I=np.zeros([nodes_num, nodes_num])#subgraph matrix (to be calculated)
        P=np.zeros([nodes_num, self.node_max])#permutation matrix
        #When calculating, use P.I.adj.I.(P.transpose())
        for i in range(nodes_num):
            if permu[0][i]==1:
                I[i][i]=1
        for i in range(len(permu[1])):
            if permu[0][i]==1:
                P[i,int(permu[1][i])]=1
        return (I,P)

    def permutation(self, observation=None):#find the active points and embedding into node_max dims by permutations
        self.permu=np.zeros([2,self.nodes])#permu[0] is available points and permu[1] is the place after permuted
        if observation is None:
            observation=self.observation
        actpts=self.permu[0]
        for node in range(self.nodes):
            if observation[node]==1:
                continue
            else:
                skip=True
                for i in self.env.graph_init.neighbors(node):
                    if observation[i]==0:
                        skip=False
                        break
                if skip:
                    continue
            actpts[node]=1
        permu2=random.sample(list(range(self.node_max)), int(np.sum(actpts)))
        j=0
        for i in range(self.nodes):
            if actpts[i]==1:
                self.permu[1][i]=permu2[j]
                j+=1

    def act(self, aux): # eps-greedy
        with torch.no_grad():
            action = 0
            if self.epsilon_ > np.random.rand():
		print("Let's try to understand what is self.permu[0,:]")
                print(self.permu[0,:]) #
                action = int(np.random.choice(np.where(self.permu[0,:] == 1)[0]))
            else:
                (I,P)=self.permutation_array()
                mul_mat = np.matmul(I,P)
                adj1 = np.matmul(mul_mat.transpose(), self.graphs[self.games].adj())
                adj2 = np.matmul(adj1, mul_mat)
                feat1 = self.permu[0].reshape(1,self.nodes)
                feat2 = np.matmul(feat1, P)
                feat3 = np.repeat(feat2.reshape(1,self.node_max,1), 2, axis=2)
                node_feat = torch.tensor(feat3, dtype=torch.float)
                aux_tensor=torch.tensor(aux, dtype=torch.float).unsqueeze(dim=0)
                adj2_tensor=torch.tensor(adj2,dtype=torch.float).unsqueeze(dim=0)
                q_a = self.model.forward(node_feat.to(self.device), adj2_tensor.to(self.device), aux_tensor.to(self.device)).cpu() #forward propagate only, ADJ here should be ADJ_subgraph
                q_a_np=q_a.squeeze_().numpy() #Avail_pts RATHER THAN observation for forward processing!!!
                q_a0=np.matmul(q_a_np, P.transpose())
                max_value=float("-inf")
                for i in range(self.nodes):
                    if self.permu[0,i] == 0:
                        continue
                    if q_a0[i]>max_value:
                        max_value=q_a0[i]
                        action=i
            # get the point cover ratio and edge cover ratio
            # Using LOCAL variables to prevent unexpected changes of variables
            (reward,done) = self.env.act(action)
            self.remember(self.permu.copy(), action, reward, aux)
            self.iter += 1
        return (reward, done)

    def renew(self,recent):
            # Warning: you should play the game several times (such as 1000) to start the optimizing process.
        if recent:#choose the recent rounds?
            exp_sam = random.sample(self.memory_n[:-20], self.minibatch_length-20)
            exp_sam_2=self.memory_n[-20:]
            exp_sam=exp_sam+exp_sam_2
        else:
            exp_sam = random.sample(self.memory_n, self.minibatch_length)
        l_feat_tens=torch.empty(self.minibatch_length, self.node_max,2)
        action_tens=torch.empty(self.minibatch_length)
        reward_tens=torch.empty(self.minibatch_length)
        feat_tens=torch.empty(self.minibatch_length, self.node_max,2)
        done_tens=torch.empty(self.minibatch_length, dtype=torch.int)
        l_adj_tens=torch.empty(self.minibatch_length, self.node_max, self.node_max)
        adj_tens = torch.empty(self.minibatch_length, self.node_max, self.node_max)
        l_aux_tens=torch.empty(self.minibatch_length, 3)
        aux_tens=torch.empty(self.minibatch_length, 3)
        target=torch.zeros(self.minibatch_length)
        permus=[None]*self.minibatch_length
        for i in range(self.minibatch_length):
            (I1,P1)=self.permutation_array(exp_sam[i][0])
            mul_mat1 = np.matmul(I1,P1)
            adj1 = np.matmul(mul_mat1.transpose(), self.graphs[exp_sam[i][5]].adj())
            adj1_ = np.matmul(adj1, mul_mat1)
            feat1 = exp_sam[i][0][0].reshape(1,self.graphs[exp_sam[i][5]].nodes_count())
            feat1_ = np.matmul(feat1, P1)
            feat1__ = np.repeat(feat1_.reshape(self.node_max,1), 2, axis=1)
            (I2,P2)=self.permutation_array(exp_sam[i][3])
            mul_mat2 = np.matmul(I2,P2)
            adj2 = np.matmul(mul_mat2.transpose(), self.graphs[exp_sam[i][5]].adj())
            adj2_ = np.matmul(adj2, mul_mat1)
            feat2 = exp_sam[i][3][0].reshape(1,self.graphs[exp_sam[i][5]].nodes_count())
            feat2_ = np.matmul(feat2, P2)
            feat2__ = np.repeat(feat2_.reshape(self.node_max,1), 2, axis=1)

            l_feat_tens[i]=torch.tensor(feat1__)#torch.zeros(1, 2).scatter_(1, exp_sam[i][0], 1)
            action_tens[i]=exp_sam[i][1]
            reward_tens[i]=exp_sam[i][2]
            feat_tens[i]=torch.tensor(feat2__)#torch.zeros(1, 2).scatter_(1, exp_sam[i][3], 1)
            done_tens[i]=int(exp_sam[i][4])
            l_adj_tens[i] = torch.from_numpy(adj1_).type(torch.FloatTensor)
            adj_tens[i] = torch.from_numpy(adj2_).type(torch.FloatTensor)
            l_aux_tens[i] = torch.tensor(exp_sam[i][6])
            aux_tens[i] = torch.tensor(exp_sam[i][7])
            permus[i]=P2
        self.optimizer.zero_grad()
        m1=self.model.forward(feat_tens.to(self.device), adj_tens.to(self.device), aux_tens.to(self.device)).cpu()#feat
        m1.squeeze_(dim=-1)
        for i in range(self.minibatch_length):
            m2=torch.matmul(m1[i], torch.tensor(permus[i].transpose(),dtype=torch.float))
            if done_tens[i]==0:#need to change to NON_ZERO max
                m0=~torch.eq(m2,0) # We had to change the syntax due to change in PyTorch
                m00=torch.masked_select(m2, m0)
                target[i] = torch.max(m00)
        target *= self.gamma
        target += reward_tens#max should be selected among the active pts.
        target_p=torch.zeros_like(target)
        p_tensor=self.model(l_feat_tens.to(self.device), l_adj_tens.to(self.device), l_aux_tens.to(self.device)).cpu()#l_feat
        for i in range(self.minibatch_length):
            target_p[i] = p_tensor[i,exp_sam[i][1],:]
        loss=self.criterion(target_p, target)
        if(self.games%100==0):
            print(loss)
        loss.backward()
        self.optimizer.step()
        if self.epsilon_ > self.epsilon_min:
           self.epsilon_ *= self.discount_factor

    def remember(self, permu, action, reward, aux): #You can change it to TEMPORAL data!!
    		# aux: we never use it.
        self.memory.append((permu, action, reward, aux))

    def remember_n(self):#save n-step experience
        cum_reward=0
        for i in range(self.n_step):
            cum_reward += self.memory[i][2] #r0+...+r(i-1)
        for i in range(self.iter):
            done = (i+self.n_step > self.iter - 1)
            if done:
                step_init = (self.memory[i][0], self.memory[i][1], cum_reward, self.zpad, done, self.games, self.memory[i][3], [1.0*self.observation.sum().item(),1.0,1.0])
            else:
                step_init = (self.memory[i][0], self.memory[i][1], cum_reward, self.memory[i+self.n_step][0], done, self.games, self.memory[i][3], self.memory[i+self.n_step][3])
            self.memory_n.append(step_init)
            if not done: cum_reward += self.memory[i+self.n_step][2]
            cum_reward -= self.memory[i][2]

    def save_model(self):
        cwd = os.getcwd()
        torch.save(self.model.state_dict(), cwd+'/model.pt')

    def graph_reset(self,graphs):
        self.graphs = graphs
        self.env.graph_reset(graphs)

    def change_to_test(self, test_graphs):
        self.graph_reset(test_graphs)
        self.epsilon_=0


Agent = DQAgent #alias
