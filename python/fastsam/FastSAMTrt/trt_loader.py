import pycuda.driver as cuda
import pycuda.autoinit
import numpy as np
import atexit

import tensorrt as trt

TRT_LOGGER = trt.Logger()
trt.init_libnvinfer_plugins(TRT_LOGGER, '')

# TensorRT version check
TRT_VERSION = int(trt.__version__.split('.')[0])
print(f"[Info] TensorRT version: {trt.__version__}, Major: {TRT_VERSION}")

# Global list to track all TRT models for cleanup
_trt_models = []

# Simple helper data class that's a little nicer to use than a 2-tuple.
class HostDeviceMem(object):
    def __init__(self, host_mem, device_mem, name=None, shape=None):
        self.host = host_mem
        self.device = device_mem
        self.name = name  # tensor name for TRT 10.0+
        self.shape = shape

    def __str__(self):
        return "Host:\n" + str(self.host) + "\nDevice:\n" + str(self.device)

    def __repr__(self):
        return self.__str__()

# Allocates all buffers required for an engine, i.e. host/device inputs/outputs.
def allocate_buffers(engine, max_boxes, total_classes):
    inputs = []
    outputs = []
    bindings = []
    stream = cuda.Stream()
    out_shapes = []
    input_shapes = []
    out_names = []
    max_batch_size = engine.get_profile_shape(0, 0)[2][0]
    print('Profile shape: ', engine.get_profile_shape(0, 0))
    # max_batch_size = 1
    for binding in engine:
        binding_shape = engine.get_binding_shape(binding)
        #Fix -1 dimension for proper memory allocation for batch_size > 1
        if binding == 'input':
            max_width = engine.get_profile_shape(0, 0)[2][3]
            max_height = engine.get_profile_shape(0, 0)[2][2]
            size = max_batch_size * max_width * max_height * 3
        else:
            size = max_batch_size * max_boxes * (total_classes + 5)
        dtype = trt.nptype(engine.get_binding_dtype(binding))
        # Allocate host and device buffers
        host_mem = cuda.pagelocked_empty(size, dtype)
        device_mem = cuda.mem_alloc(host_mem.nbytes)
        # Append the device buffer to device bindings.
        bindings.append(int(device_mem))
        # Append to the appropriate list.
        if engine.binding_is_input(binding):
            inputs.append(HostDeviceMem(host_mem, device_mem))
            input_shapes.append(engine.get_binding_shape(binding))
        else:
            outputs.append(HostDeviceMem(host_mem, device_mem))
            #Collect original output shapes and names from engine
            out_shapes.append(engine.get_binding_shape(binding))
            out_names.append(binding)
    return inputs, outputs, bindings, stream, input_shapes, out_shapes, out_names, max_batch_size

def allocate_buffers_nms(engine):
    """Allocate buffers for TensorRT 10.0+ API"""
    inputs = []
    outputs = []
    bindings = []
    stream = cuda.Stream()
    out_shapes = []
    input_shapes = []
    out_names = []
    
    if TRT_VERSION >= 10:
        # TensorRT 10.0+ API
        # Get the first input tensor name to query profile shape
        first_input_name = None
        for i in range(engine.num_io_tensors):
            name = engine.get_tensor_name(i)
            if engine.get_tensor_mode(name) == trt.TensorIOMode.INPUT:
                first_input_name = name
                break
        
        profile_shapes = engine.get_tensor_profile_shape(first_input_name, 0)
        max_batch_size = profile_shapes[2][0]  # max shape
        print('Profile shape: ', profile_shapes)
        
        for i in range(engine.num_io_tensors):
            name = engine.get_tensor_name(i)
            binding_shape = engine.get_tensor_shape(name)
            print('binding:', name, '- binding_shape:', binding_shape)
            
            if engine.get_tensor_mode(name) == trt.TensorIOMode.INPUT:
                # Input tensor
                max_width = profile_shapes[2][3]
                max_height = profile_shapes[2][2]
                size = max_batch_size * max_width * max_height * 3
                dtype = trt.nptype(engine.get_tensor_dtype(name))
                host_mem = cuda.pagelocked_empty(size, dtype)
                device_mem = cuda.mem_alloc(host_mem.nbytes)
                bindings.append(int(device_mem))
                inputs.append(HostDeviceMem(host_mem, device_mem, name=name, shape=binding_shape))
                input_shapes.append(binding_shape)
            else:
                # Output tensor
                binding_shape_tuple = tuple(binding_shape)
                adjusted_shape = (max_batch_size,) + binding_shape_tuple[1:]
                size = trt.volume(adjusted_shape)
                dtype = trt.nptype(engine.get_tensor_dtype(name))
                host_mem = cuda.pagelocked_empty(size, dtype)
                device_mem = cuda.mem_alloc(host_mem.nbytes)
                bindings.append(int(device_mem))
                outputs.append(HostDeviceMem(host_mem, device_mem, name=name, shape=adjusted_shape))
                out_shapes.append(adjusted_shape[1:])
                out_names.append(name)
    else:
        # TensorRT 8.x API (legacy)
        max_batch_size = engine.get_profile_shape(0, 0)[2][0]
        print('Profile shape: ', engine.get_profile_shape(0, 0))
        for binding in engine:
            binding_shape = engine.get_binding_shape(binding)
            print('binding:', binding, '- binding_shape:', binding_shape)
            if binding == 'input':
                max_width = engine.get_profile_shape(0, 0)[2][3]
                max_height = engine.get_profile_shape(0, 0)[2][2]
                size = max_batch_size * max_width * max_height * 3
            else:
                binding_shape = (max_batch_size,) + binding_shape[1:]
                size = trt.volume(binding_shape)
            dtype = trt.nptype(engine.get_binding_dtype(binding))
            host_mem = cuda.pagelocked_empty(size, dtype)
            device_mem = cuda.mem_alloc(host_mem.nbytes)
            bindings.append(int(device_mem))
            if engine.binding_is_input(binding):
                inputs.append(HostDeviceMem(host_mem, device_mem))
                input_shapes.append(engine.get_binding_shape(binding))
            else:
                outputs.append(HostDeviceMem(host_mem, device_mem))
                out_shapes.append(binding_shape[1:])
                out_names.append(binding)
    
    return inputs, outputs, bindings, stream, input_shapes, out_shapes, out_names, max_batch_size
# This function is generalized for multiple inputs/outputs.
# inputs and outputs are expected to be lists of HostDeviceMem objects.
def do_inference(context, bindings, inputs, outputs, stream):
    # Transfer input data to the GPU.
    [cuda.memcpy_htod_async(inp.device, inp.host, stream) for inp in inputs]
    
    if TRT_VERSION >= 10:
        # TensorRT 10.0+ API: set tensor addresses and use execute_async_v3
        for inp in inputs:
            context.set_tensor_address(inp.name, int(inp.device))
        for out in outputs:
            context.set_tensor_address(out.name, int(out.device))
        context.execute_async_v3(stream_handle=stream.handle)
    else:
        # TensorRT 8.x API
        context.execute_async_v2(bindings=bindings, stream_handle=stream.handle)
    
    # Transfer predictions back from the GPU.
    [cuda.memcpy_dtoh_async(out.host, out.device, stream) for out in outputs]
    # Synchronize the stream
    stream.synchronize()
    # Return only the host outputs.
    return [out.host for out in outputs]

class TrtModel(object):
    def __init__(self, model, max_size, total_classes = 80):
        self.engine_file = model
        self.engine = None
        self.inputs = None
        self.outputs = None
        self.bindings = None
        self.stream = None
        self.context = None
        self.input_shapes = None
        self.out_shapes = None
        self.max_batch_size = 1
        self.max_size = max_size
        self.total_classes = total_classes

    def build(self):
        with open(self.engine_file, 'rb') as f, trt.Runtime(TRT_LOGGER) as runtime:
            self.engine = runtime.deserialize_cuda_engine(f.read())
        # Allocate
        self.max_boxes = self.get_number_of_boxes(self.max_size, self.max_size)
        print('Maximum image size: {}x{}'.format(self.max_size, self.max_size))
        print('Maximum boxes: {}'.format(self.max_boxes))
        self.inputs, self.outputs, self.bindings, self.stream, self.input_shapes, self.out_shapes, self.out_names, self.max_batch_size = \
                allocate_buffers(self.engine, max_boxes = self.max_boxes, total_classes = self.total_classes)
        # print(self.inputs, self.outputs, self.bindings, self.stream, self.input_shapes, self.out_shapes, self.out_names, self.max_batch_size)
        self.context = self.engine.create_execution_context()
        self.context.active_optimization_profile = 0

    def get_number_of_boxes(self, im_width, im_height):
        # Calculate total boxes (3 detect layers)
        assert im_width % 32 == 0 and im_height % 32 == 0
        return (int(im_width*im_height/32/32) + int(im_width*im_height/16/16) + int(im_width*im_height/8/8))*3

    def run(self, input, deflatten: bool = True, as_dict = False):
        # lazy load implementation
        if self.engine is None:
            self.build()

        input = np.asarray(input)
        batch_size, _, im_height, im_width = input.shape
        assert batch_size <= self.max_batch_size
        assert max(im_width, im_height) <= self.max_size, "Invalid shape: {}x{}, max shape: {}".format(im_width, im_height, self.max_size)
        allocate_place = np.prod(input.shape)
        # print('allocate_place', input.shape)
        self.inputs[0].host[:allocate_place] = input.flatten(order='C').astype(np.float32)
        self.context.set_binding_shape(0, input.shape)
        trt_outputs = do_inference(
            self.context, bindings=self.bindings,
            inputs=self.inputs, outputs=self.outputs, stream=self.stream)
        # print(self.inputs, self.outputs, self.bindings, self.stream, self.input_shapes, self.out_shapes, self.out_names, self.max_batch_size)
        # Reshape TRT outputs to original shape instead of flattened array
        # print(trt_outputs[0].shape)
        if deflatten:
            out_shapes = [(batch_size, ) + (self.get_number_of_boxes(im_width, im_height), 85)]
            trt_outputs = [output[:np.prod(shape)].reshape(shape) for output, shape in zip(trt_outputs, out_shapes)]
        if as_dict:
            return {self.out_names[ix]: trt_output[:batch_size] for ix, trt_output in enumerate(trt_outputs)}
        return [trt_output[:batch_size] for trt_output in trt_outputs]


def _cleanup_trt_models():
    """Cleanup all TRT models before program exit."""
    for model in _trt_models:
        try:
            model.destroy()
        except:
            pass
    _trt_models.clear()

# Register cleanup function
atexit.register(_cleanup_trt_models)


class TrtModelNMS(object):
    def __init__(self, model, max_size):
        self.engine_file = model
        self.engine = None
        self.inputs = None
        self.outputs = None
        self.bindings = None
        self.stream = None
        self.context = None
        self.input_shapes = None
        self.out_shapes = None
        self.max_batch_size = 1
        self.max_size = max_size
        self._destroyed = False
        # Register for cleanup
        _trt_models.append(self)

    def build(self):
        with open(self.engine_file, 'rb') as f, trt.Runtime(TRT_LOGGER) as runtime:
            self.engine = runtime.deserialize_cuda_engine(f.read())
        # Allocate
        self.inputs, self.outputs, self.bindings, self.stream, self.input_shapes, self.out_shapes, self.out_names, self.max_batch_size = \
                allocate_buffers_nms(self.engine)
        self.context = self.engine.create_execution_context()
        
        if TRT_VERSION >= 10:
            # TensorRT 10.0+ uses set_optimization_profile_async or direct profile setting
            self.context.set_optimization_profile_async(0, self.stream.handle)
            self.stream.synchronize()
        else:
            self.context.active_optimization_profile = 0

    def destroy(self):
        """Explicitly release TensorRT and CUDA resources."""
        if self._destroyed:
            return
        self._destroyed = True
        
        # Synchronize stream before cleanup
        if self.stream is not None:
            try:
                self.stream.synchronize()
            except:
                pass
        
        # Free device memory
        if self.inputs is not None:
            for inp in self.inputs:
                try:
                    inp.device.free()
                except:
                    pass
        
        if self.outputs is not None:
            for out in self.outputs:
                try:
                    out.device.free()
                except:
                    pass
        
        # Release context and engine
        if self.context is not None:
            del self.context
            self.context = None
        
        if self.engine is not None:
            del self.engine
            self.engine = None
        
        self.stream = None
        self.inputs = None
        self.outputs = None
        self.bindings = None

    def __del__(self):
        self.destroy()

    def run(self, input, deflatten: bool = True, as_dict = False):
        # lazy load implementation
        if self.engine is None:
            self.build()

        input = np.asarray(input)
        batch_size, _, im_height, im_width = input.shape
        assert batch_size <= self.max_batch_size
        assert max(im_width, im_height) <= self.max_size, "Invalid shape: {}x{}, max shape: {}".format(im_width, im_height, self.max_size)
        allocate_place = np.prod(input.shape)
        self.inputs[0].host[:allocate_place] = input.flatten(order='C').astype(np.float32)
        
        if TRT_VERSION >= 10:
            # TensorRT 10.0+ API
            input_name = self.inputs[0].name
            self.context.set_input_shape(input_name, input.shape)
        else:
            # TensorRT 8.x API
            self.context.set_binding_shape(0, input.shape)
        
        trt_outputs = do_inference(
            self.context, bindings=self.bindings,
            inputs=self.inputs, outputs=self.outputs, stream=self.stream)
        
        if deflatten:
            out_shapes = [(batch_size, ) + self.out_shapes[ix] for ix in range(len(self.out_shapes))]
            trt_outputs = [output[:np.prod(shape)].reshape(shape) for output, shape in zip(trt_outputs, out_shapes)]
        if as_dict:
            return {self.out_names[ix]: trt_output[:batch_size] for ix, trt_output in enumerate(trt_outputs)}
        return [trt_output[:batch_size] for trt_output in trt_outputs]