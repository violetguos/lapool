from explainer.backprop import GradxInputExplainer
import types
import torch.nn.functional as F

# Based on formulation in DeepExplain, https://arxiv.org/abs/1711.06104
# https://github.com/marcoancona/DeepExplain/blob/master/deepexplain/tensorflow/methods.py#L221-L272
class DeepLIFTRescaleExplainer(GradxInputExplainer):
    def __init__(self, model):
        super(DeepLIFTRescaleExplainer, self).__init__(model)
        self._prepare_reference()
        self.baseline_inp = None
        self._override_backward()

    def _prepare_reference(self):
        def init_refs(m):
            name = m.__class__.__name__
            if name.find('ReLU') != -1:
                m.ref_inp_list = []
                m.ref_out_list = []

        def ref_forward(self, x):
            self.ref_inp_list.append(x.clone())
            out = F.relu(x)
            self.ref_out_list.append(out.clone())
            return out

        def ref_replace(m):
            name = m.__class__.__name__
            if name.find('ReLU') != -1:
                m.forward = types.MethodType(ref_forward, m)

        self.model.apply(init_refs)
        self.model.apply(ref_replace)

    def _reset_preference(self):
        def reset_refs(m):
            name = m.__class__.__name__
            if name.find('ReLU') != -1:
                m.ref_inp_list = []
                m.ref_out_list = []

        self.model.apply(reset_refs)

    def _baseline_forward(self, inp):
        if self.baseline_inp is None:
            self.baseline_inp = [x.clone().fill(0.0) for x in inp]
        else:
            self.baseline_inp = [x.fill(0.0) for x in self.baseline_inp] 
        # get ref
        self.baseline_inp = [x.unsqueeze(0).require_grad_() for x in self.baseline_inp]
        _ = self.model(self.baseline_inp)

    def _override_backward(self):
        def new_backward(self, grad_out):
            ref_inp, inp = self.ref_inp_list
            ref_out, out = self.ref_out_list
            delta_out = out - ref_out
            delta_in = inp - ref_inp
            g1 = (delta_in.abs() > 1e-5).float() * grad_out * \
                 delta_out / delta_in
            mask = ((ref_inp + inp) > 0).float()
            g2 = (delta_in.abs() <= 1e-5).float() * 0.5 * mask * grad_out

            return g1 + g2

        def backward_replace(m):
            name = m.__class__.__name__
            if name.find('ReLU') != -1:
                m.backward = types.MethodType(new_backward, m)

        self.model.apply(backward_replace)

    def explain(self, inp, ind=None, grad_ind=-1):
        self._reset_preference()
        self._baseline_forward(inp, grad_ind)
        g = super(DeepLIFTRescaleExplainer, self).explain(inp, ind, grad_ind)

        return g
