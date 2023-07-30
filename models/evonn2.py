import math
import random
from typing import List, Tuple

import torch
from torch import nn, Tensor
import torch.nn.functional as F
# from .STAW import graphattention

class nconv(nn.Module):
    def __init__(self):
        super(nconv,self).__init__()

    def forward(self,x, A):
        x = torch.einsum('ncvl,vw->ncwl',(x,A))
        return x.contiguous()

class graphattention(nn.Module):
    def __init__(self,c_in,c_out,dropout,d=16, emb_length=0, aptonly=False, noapt=False):
        super(graphattention,self).__init__()
        self.d = d
        self.aptonly = aptonly
        self.noapt = noapt
        self.mlp = linear(c_in*2,c_out)
        self.dropout = dropout
        self.emb_length = emb_length
        if aptonly:
            self.qm = FC(self.emb_length, d)  # query matrix
            self.km = FC(self.emb_length, d)  # key matrix
        elif noapt:
            self.qm = FC(c_in, d)  # query matrix
            self.km = FC(c_in, d)  # key matrix
        else:
            
            self.qm = FC(c_in + self.emb_length, d)  # query matrix
            self.km = FC(c_in + self.emb_length, d)  # key matrix

    def forward(self,x,embedding):
        # x: [batch_size, D, nodes, time_step]
        # embedding = [10, num_nodes]
        out = [x]

        embedding = embedding.repeat((x.shape[0], x.shape[-1], 1, 1)) # embedding = [batch_size, time_step, 10, num_nodes]
        embedding = embedding.permute(0,2,3,1) # embedding = [batch_size, 16, num_nodes, time_step]

        if self.aptonly:
            x_embedding = embedding
            query = self.qm(x_embedding).permute(0, 3, 2, 1)
            key = self.km(x_embedding).permute(0, 3, 2, 1)  #
            # value = self.vm(x)
            attention = torch.matmul(query,key.permute(0, 1, 3, 2))  # attention=[batch_size, time_step, num_nodes, num_nodes]
            # attention = F.relu(attention)
            attention /= (self.d ** 0.5)
            attention = F.softmax(attention, dim=-1)
        elif self.noapt:
            x_embedding = x
            query = self.qm(x_embedding).permute(0, 3, 2, 1)  # query=[batch_size, time_step, num_nodes, d]
            key = self.km(x_embedding).permute(0, 3, 2, 1)  # key=[batch_size, time_step, num_nodes, d]
            attention = torch.matmul(query,key.permute(0, 1, 3, 2))  # attention=[batch_size, time_step, num_nodes, num_nodes]
            # attention = F.relu(attention)
            attention /= (self.d ** 0.5)
            attention = F.softmax(attention, dim=-1)
        else:
            x_embedding = torch.cat([x,embedding], axis=1) # x_embedding=[batch_size, D+10, num_nodes, time_step]
            query = self.qm(x_embedding).permute(0,3,2,1) # query=[batch_size, time_step, num_nodes, d]
            key = self.km(x_embedding).permute(0,3,2,1) # key=[batch_size, time_step, num_nodes, d]
            # query = F.relu(query)
            # key = F.relu(key)
            attention = torch.matmul(query, key.permute(0,1,3,2)) # attention=[batch_size, time_step, num_nodes, num_nodes]
            # attention = F.relu(attention)
            attention /= (self.d**0.5)
            attention = F.softmax(attention, dim=-1)

        x = torch.matmul(x.permute(0,3,1,2), attention).permute(0,2,3,1)
        out.append(x)

        h = torch.cat(out,dim=1)
        h = self.mlp(h)
        h = F.dropout(h, self.dropout, training=self.training)
        return h#attention


class linear(nn.Module):
    def __init__(self,c_in,c_out):
        super(linear,self).__init__()
        self.mlp = torch.nn.Conv2d(c_in, c_out, kernel_size=(1, 1), padding=(0,0), stride=(1,1), bias=True)

    def forward(self,x):
        return self.mlp(x)


class FC(nn.Module):
    def __init__(self,c_in,c_out):
        super(FC,self).__init__()
        self.mlp = torch.nn.Conv2d(c_in, c_out, kernel_size=(1, 1), padding=(0,0), stride=(1,1), bias=True)

    def forward(self,x):
        return self.mlp(x)
  
class EvolutionCell(nn.Module):
    def __init__(self, input_dim: int, output_dim: int, num_nodes: int, n_supports: int, max_step: int, layer: int, n_dim:int):
        super(EvolutionCell, self).__init__()
        self.layer = layer
        self.perceptron = nn.ModuleList()
        self.graphconv = nn.ModuleList()
        self.attlinear = nn.Linear(num_nodes * output_dim, 1)
        self.graphconv.append(GraphConv_(input_dim, output_dim, num_nodes, n_supports, max_step))
        for i in range(1, layer):
            self.graphconv.append(GraphConv_(output_dim, output_dim, num_nodes, n_supports, max_step))

    def forward(self, inputs, supports: List):
        outputs = []
        for i in range(self.layer):
            inputs = self.graphconv[i](inputs,[supports[i]])
            outputs.append(inputs)
        out = self.attention(torch.stack(outputs, dim=1))
        # out = outputs[-1]
        return out

    def attention(self, inputs: Tensor):
        b, g, n, f = inputs.size()
        x = inputs.reshape(b, g, -1)
        out = self.attlinear(x)  # (batch, graph, 1)
        weight = F.softmax(out, dim=1)

        outputs = (x * weight).sum(dim=1).reshape(b, n, f)
        return outputs


class DCGRUCell(nn.Module):
    def  __init__(self, input_size: int, hidden_size: int, num_node: int, n_supports: int, k_hop: int, e_layer: int, n_dim:int):
        super(DCGRUCell, self).__init__()
        self.hidden_size = hidden_size

        self.ru_gate_g_conv = EvolutionCell(input_size + hidden_size, hidden_size * 2, num_node, n_supports, k_hop,
                                            e_layer, n_dim)
        self.candidate_g_conv = EvolutionCell(input_size + hidden_size, hidden_size, num_node, n_supports, k_hop,
                                              e_layer, n_dim)
        self.gat=graphattention(hidden_size, hidden_size,dropout=0.3,emb_length=16, aptonly=False, noapt=False)
        self.embedding = nn.Parameter(torch.randn(16,  num_node).to('cuda:0'), requires_grad=True).to('cuda:0')
        self.weight= nn.Parameter(torch.rand(2).to('cuda:0'), requires_grad=True).to('cuda:0')
    def forward(self, inputs: Tensor, supports: List[Tensor], states) -> Tuple[Tensor, Tensor]:
        """
        :param inputs: Tensor[Batch, Node, Feature]
        :param supports:
        :param states:Tensor[Batch, Node, Hidden_size]
        :return:
        """
        r_u = torch.sigmoid(self.ru_gate_g_conv(torch.cat([inputs, states], -1), supports))
        r, u = r_u.split(self.hidden_size, -1)
        c = torch.tanh(self.candidate_g_conv(torch.cat([inputs, r * states], -1), supports))
        outputs = new_state = u * states + (1 - u) * c
        outputs=outputs.unsqueeze(-1).transpose(2, 1)
        new_state_att=outputs_att=self.gat(outputs,self.embedding).squeeze(-1).transpose(2, 1)*self.weight[0]*2+2*self.weight[1]*outputs.squeeze(-1).transpose(2, 1)

        return outputs_att, new_state_att


class DCRNNEncoder(nn.ModuleList):
    def __init__(self, input_size: int, hidden_size: int, num_node: int, n_supports: int, k_hop: int, n_layers: int,
                 e_layer: int, n_dim:int):
        super(DCRNNEncoder, self).__init__()
        self.hidden_size = hidden_size
        self.append(DCGRUCell(input_size, hidden_size, num_node, n_supports, k_hop, e_layer,n_dim))
        for _ in range(1, n_layers):
            self.append(DCGRUCell(hidden_size, hidden_size, num_node, n_supports, k_hop, e_layer,n_dim))

    def forward(self, inputs: Tensor, supports: List[Tensor]) -> Tensor:
        """
        :param inputs: tensor, [B, T, N, input_size]
        :param supports: list of sparse tensors, each of shape [N, N]
        :return: tensor, [n_layers, B, N, hidden_size]
        """

        b, t, n, _ = inputs.shape
        dv, dt = inputs.device, inputs.dtype

        states = list(torch.zeros(len(self), b, n, self.hidden_size, device=dv, dtype=dt))
        inputs = list(inputs.transpose(0, 1))

        for i_layer, cell in enumerate(self):
            for i_t in range(t):
                inputs[i_t], states[i_layer] = cell(inputs[i_t], supports, states[i_layer])

        return torch.stack(states)


class DCRNNDecoder(nn.ModuleList):
    def __init__(self, output_size: int, hidden_size: int, num_node: int,
                 n_supports: int, k_hop: int, n_layers: int, n_preds: int, e_layer: int, n_dim:int):
        super(DCRNNDecoder, self).__init__()
        self.output_size = output_size
        self.n_preds = n_preds
        self.append(DCGRUCell(output_size, hidden_size, num_node, n_supports, k_hop, e_layer, n_dim))
        for _ in range(1, n_layers):
            self.append(DCGRUCell(hidden_size, hidden_size, num_node, n_supports, k_hop, e_layer, n_dim))
        self.out = nn.Linear(hidden_size, output_size)

    def forward(self, supports: List[Tensor], states: Tensor,
                targets: Tensor = None, teacher_force: bool = 0.5) -> Tensor:
        """
        :param supports: list of sparse tensors, each of shape [N, N]
        :param states: tensor, [n_layers, B, N, hidden_size]
        :param targets: None or tensor, [B, T, N, output_size]
        :param teacher_force: random to use targets as decoder inputs
        :return: tensor, [B, T, N, output_size]
        """
        n_layers, b, n, _ = states.shape

        inputs = torch.zeros(b, n, self.output_size, device=states.device, dtype=states.dtype)

        states = list(states)
        assert len(states) == n_layers

        new_outputs = list()
        for i_t in range(self.n_preds):
            for i_layer in range(n_layers):
                inputs, states[i_layer] = self[i_layer](inputs, supports, states[i_layer])
            inputs = self.out(inputs)
            new_outputs.append(inputs)
            if targets is not None and random.random() < teacher_force:
                inputs = targets[:, i_t]

        return torch.stack(new_outputs, 1)


class EvoNN2(nn.Module):
    def __init__(self,
                 n_pred: int,
                 hidden_size: int,
                 num_nodes: int,
                 n_dim: int,
                 n_supports: int,
                 k_hop: int,
                 n_rnn_layers: int,
                 n_gconv_layers: int,
                 input_dim: int,
                 output_dim: int,
                 cl_decay_steps: int,
                 support,
                 device):
        super(EvoNN2, self).__init__()
        self.cl_decay_steps = cl_decay_steps
        self.device = device
        m, p, n = torch.svd(support)
        initemb1 = torch.mm(m[:, :n_dim], torch.diag(p[:n_dim] ** 0.5))
        initemb2 = torch.mm(torch.diag(p[:n_dim] ** 0.5), n[:, :n_dim].t())
        self.nodevec1 = nn.Parameter(initemb1, requires_grad=True)
        self.nodevec2 = nn.Parameter(initemb2, requires_grad=True)

        self.n_gconv_layers = n_gconv_layers
        self.encoder = DCRNNEncoder(input_dim, hidden_size, num_nodes, n_supports, k_hop, n_rnn_layers, n_gconv_layers,n_dim)
        self.decoder = DCRNNDecoder(output_dim, hidden_size, num_nodes, n_supports, k_hop, n_rnn_layers, n_pred,
                                    n_gconv_layers,n_dim)

        self.w1 = nn.Parameter(torch.eye(n_dim), requires_grad=True)
        self.w2 = nn.Parameter(torch.eye(n_dim), requires_grad=True)
        self.b1= nn.Parameter(torch.zeros(n_dim), requires_grad=True)
        self.b2=nn.Parameter(torch.zeros(n_dim), requires_grad=True)
        self.graph0 = None
        self.graph1 = None
        self.graph2 = None



    def forward(self, inputs: Tensor, targets: Tensor = None, batch_seen: int = None) -> Tensor:
        graph = list()
        nodevec1 = self.nodevec1
        nodevec2 = self.nodevec2
        n = nodevec1.size(0)
        self.graph0 = F.leaky_relu_(torch.mm(nodevec1, nodevec2))
        graph.append(self.graph0)


        nodevec1 = nodevec1.mm(self.w1) + self.b1.repeat(n, 1)
        nodevec2 = (nodevec2.T.mm(self.w1) + self.b1.repeat(n, 1)).T
        self.graph1 = F.leaky_relu_(torch.mm(nodevec1, nodevec2))
        graph.append(self.graph1)
        nodevec1 = nodevec1.mm(self.w2) + self.b2.repeat(n, 1)
        nodevec2 = (nodevec2.T.mm(self.w2) + self.b2.repeat(n, 1)).T
        self.graph2 = F.leaky_relu_(torch.mm(nodevec1, nodevec2))
        graph.append(self.graph2)
        states = self.encoder(inputs, graph)
        outputs = self.decoder(graph, states, targets, self._compute_sampling_threshold(batch_seen))
        return outputs, graph

    def _compute_sampling_threshold(self, batches_seen: int):
        return self.cl_decay_steps / (self.cl_decay_steps + math.exp(batches_seen / self.cl_decay_steps))


class GraphConv_(nn.Module):
    def __init__(self, input_dim: int, output_dim: int, num_nodes: int, n_supports: int, max_step: int):
        super(GraphConv_, self).__init__()
        self._num_nodes = num_nodes
        self._max_diffusion_step = max_step
        num_metrics = max_step * n_supports + 1
        self.out = nn.Linear(input_dim * num_metrics, output_dim)

    @staticmethod
    def _concat(x, x_):
        x_ = torch.unsqueeze(x_, 0)
        return torch.cat([x, x_], dim=0)

    def forward(self,
                inputs: Tensor,
                supports: List[Tensor]):

        b, n, input_dim = inputs.shape
        x = inputs
        x0 = x.permute([1, 2, 0]).reshape(n, -1)  # (num_nodes, input_dim * batch_size)
        x = x0.unsqueeze(dim=0)  # (1, num_nodes, input_dim * batch_size)

        if self._max_diffusion_step == 0:
            pass
        else:
            for support in supports:
                x1 = support.mm(x0)
                x = self._concat(x, x1)
                for k in range(2, self._max_diffusion_step + 1):
                    x2 = 2 * support.mm(x1) - x0
                    x = self._concat(x, x2)
                    x1, x0 = x2, x1

        x = x.reshape(-1, n, input_dim, b).transpose(0, 3)  # (batch_size, num_nodes, input_dim, num_matrices)
        x = x.reshape(b, n, -1)  # (batch_size, num_nodes, input_dim * num_matrices)

        return self.out(x)  # (batch_size, num_nodes, output_dim)

