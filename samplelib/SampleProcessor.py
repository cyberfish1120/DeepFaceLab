import collections
from enum import IntEnum

import cv2
import numpy as np

from core import imagelib
from facelib import FaceType, LandmarksProcessor

class SampleProcessor(object):
    class SampleType(IntEnum):
        NONE = 0
        FACE_IMAGE = 1
        FACE_MASK  = 2
        LANDMARKS_ARRAY            = 3
        PITCH_YAW_ROLL             = 4
        PITCH_YAW_ROLL_SIGMOID     = 5

    class ChannelType(IntEnum):
        NONE = 0
        BGR                   = 1  #BGR
        G                     = 2  #Grayscale
        GGG                   = 3  #3xGrayscale
        BGR_SHUFFLE           = 4  #BGR shuffle
        BGR_RANDOM_HSV_SHIFT  = 5
        BGR_RANDOM_RGB_LEVELS = 6
        G_MASK                = 7

    class FaceMaskType(IntEnum):
        NONE          = 0
        ALL_HULL      = 1  #mask all hull as grayscale
        EYES_HULL     = 2  #mask eyes hull as grayscale
        ALL_EYES_HULL = 3  #combo all + eyes as grayscale
        STRUCT        = 4  #mask structure as grayscale

    class Options(object):
        def __init__(self, random_flip = True, rotation_range=[-10,10], scale_range=[-0.05, 0.05], tx_range=[-0.05, 0.05], ty_range=[-0.05, 0.05] ):
            self.random_flip = random_flip
            self.rotation_range = rotation_range
            self.scale_range = scale_range
            self.tx_range = tx_range
            self.ty_range = ty_range

    @staticmethod
    def process (samples, sample_process_options, output_sample_types, debug, ct_sample=None):
        SPST = SampleProcessor.SampleType
        SPCT = SampleProcessor.ChannelType
        SPFMT = SampleProcessor.FaceMaskType

        sample_rnd_seed = np.random.randint(0x80000000)

        outputs = []
        for sample in samples:
            sample_bgr = sample.load_bgr()
            ct_sample_bgr = None
            h,w,c = sample_bgr.shape

            is_face_sample = sample.landmarks is not None

            if debug and is_face_sample:
                LandmarksProcessor.draw_landmarks (sample_bgr, sample.landmarks, (0, 1, 0))

            params = imagelib.gen_warp_params(sample_bgr, sample_process_options.random_flip, rotation_range=sample_process_options.rotation_range, scale_range=sample_process_options.scale_range, tx_range=sample_process_options.tx_range, ty_range=sample_process_options.ty_range )

            outputs_sample = []
            for opts in output_sample_types:
                sample_type    = opts.get('sample_type', SPST.NONE)
                channel_type   = opts.get('channel_type', SPCT.NONE)                
                resolution     = opts.get('resolution', 0)
                warp           = opts.get('warp', False)
                transform      = opts.get('transform', False)
                motion_blur    = opts.get('motion_blur', None)
                gaussian_blur  = opts.get('gaussian_blur', None)
                normalize_tanh = opts.get('normalize_tanh', False)
                ct_mode        = opts.get('ct_mode', 'None')
                data_format    = opts.get('data_format', 'NHWC')
                
                if sample_type == SPST.FACE_IMAGE or sample_type == SPST.FACE_MASK:
                    if not is_face_sample:    
                        raise ValueError("face_samples should be provided for sample_type FACE_*")
                    
                if is_face_sample:    
                    face_type      = opts.get('face_type', None)
                    face_mask_type = opts.get('face_mask_type', SPFMT.NONE)
                
                    if face_type is None:
                        raise ValueError("face_type must be defined for face samples")

                    if face_type > sample.face_type:
                        raise Exception ('sample %s type %s does not match model requirement %s. Consider extract necessary type of faces.' % (sample.filename, sample.face_type, target_ft) )

                if sample_type == SPST.FACE_IMAGE or sample_type == SPST.FACE_MASK:

                    if sample_type == SPST.FACE_MASK:
                        if face_mask_type == SPFMT.ALL_HULL or \
                           face_mask_type == SPFMT.EYES_HULL or \
                           face_mask_type == SPFMT.ALL_EYES_HULL:
                            if face_mask_type == SPFMT.ALL_HULL or \
                               face_mask_type == SPFMT.ALL_EYES_HULL:
                                if sample.eyebrows_expand_mod is not None:
                                    all_mask = LandmarksProcessor.get_image_hull_mask (sample_bgr.shape, sample.landmarks, eyebrows_expand_mod=sample.eyebrows_expand_mod )
                                else:
                                    all_mask = LandmarksProcessor.get_image_hull_mask (sample_bgr.shape, sample.landmarks)

                                all_mask = np.clip(all_mask, 0, 1)

                            if face_mask_type == SPFMT.EYES_HULL or \
                               face_mask_type == SPFMT.ALL_EYES_HULL:
                                eyes_mask = LandmarksProcessor.get_image_eye_mask (sample_bgr.shape, sample.landmarks)
                                eyes_mask = np.clip(eyes_mask, 0, 1)

                            if face_mask_type == SPFMT.ALL_HULL:
                                img = all_mask
                            elif face_mask_type == SPFMT.EYES_HULL:
                                img = eyes_mask
                            elif face_mask_type == SPFMT.ALL_EYES_HULL:
                                img = all_mask + eyes_mask
                        elif face_mask_type == SPFMT.STRUCT:
                            if sample.eyebrows_expand_mod is not None:
                                img = LandmarksProcessor.get_face_struct_mask (sample_bgr.shape, sample.landmarks, eyebrows_expand_mod=sample.eyebrows_expand_mod )
                            else:
                                img = LandmarksProcessor.get_face_struct_mask (sample_bgr.shape, sample.landmarks)

                        if sample.ie_polys is not None:
                            sample.ie_polys.overlay_mask(img)

                        if sample.face_type == FaceType.MARK_ONLY:
                            mat  = LandmarksProcessor.get_transform_mat (sample.landmarks, sample.shape[0], face_type)
                            img = cv2.warpAffine( img, mat, (sample.shape[0],sample.shape[0]), flags=cv2.INTER_LINEAR )
                            img = imagelib.warp_by_params (params, img, warp, transform, can_flip=True, border_replicate=False, cv2_inter=cv2.INTER_LINEAR)
                            img = cv2.resize( img, (resolution,resolution), cv2.INTER_LINEAR )[...,None]
                        else:
                            mat = LandmarksProcessor.get_transform_mat (sample.landmarks, resolution, face_type)
                            img = imagelib.warp_by_params (params, img, warp, transform, can_flip=True, border_replicate=False, cv2_inter=cv2.INTER_LINEAR)
                            img = cv2.warpAffine( img, mat, (resolution,resolution), borderMode=cv2.BORDER_CONSTANT, flags=cv2.INTER_LINEAR )[...,None]

                        if channel_type == SPCT.G:
                            out_sample = img.astype(np.float32)
                        else:
                            raise ValueError("only channel_type.G supported for the mask")

                    elif sample_type == SPST.FACE_IMAGE:
                        img = sample_bgr
                        if motion_blur is not None:
                            chance, mb_max_size = motion_blur
                            chance = np.clip(chance, 0, 100)

                            l_rnd_state = np.random.RandomState (sample_rnd_seed)
                            mblur_rnd_chance = l_rnd_state.randint(100)
                            mblur_rnd_kernel = l_rnd_state.randint(mb_max_size)+1
                            mblur_rnd_deg    = l_rnd_state.randint(360)

                            if mblur_rnd_chance < chance:
                                img = imagelib.LinearMotionBlur (img, mblur_rnd_kernel, mblur_rnd_deg )

                        if gaussian_blur is not None:
                            chance, kernel_max_size = gaussian_blur
                            chance = np.clip(chance, 0, 100)

                            l_rnd_state = np.random.RandomState (sample_rnd_seed+1)
                            gblur_rnd_chance = l_rnd_state.randint(100)
                            gblur_rnd_kernel = l_rnd_state.randint(kernel_max_size)*2+1

                            if gblur_rnd_chance < chance:
                                img = cv2.GaussianBlur(img, (gblur_rnd_kernel,) *2 , 0)

                        if sample.face_type == FaceType.MARK_ONLY:
                            mat  = LandmarksProcessor.get_transform_mat (sample.landmarks, sample.shape[0], face_type)
                            img  = cv2.warpAffine( img,  mat, (sample.shape[0],sample.shape[0]), flags=cv2.INTER_CUBIC )
                            img  = imagelib.warp_by_params (params, img,  warp, transform, can_flip=True, border_replicate=True)
                            img  = cv2.resize( img,  (resolution,resolution), cv2.INTER_CUBIC )
                        else:
                            mat = LandmarksProcessor.get_transform_mat (sample.landmarks, resolution, face_type)
                            img  = imagelib.warp_by_params (params, img,  warp, transform, can_flip=True, border_replicate=True)
                            img  = cv2.warpAffine( img, mat, (resolution,resolution), borderMode=cv2.BORDER_REPLICATE, flags=cv2.INTER_CUBIC )

                        img = np.clip(img.astype(np.float32), 0, 1)

                        # Apply random color transfer                        
                        if ct_mode is not None and ct_sample is not None:
                            if ct_sample_bgr is None:
                               ct_sample_bgr = ct_sample.load_bgr()
                            img = imagelib.color_transfer (ct_mode, img, cv2.resize( ct_sample_bgr, (resolution,resolution), cv2.INTER_LINEAR ) )

                        # Transform from BGR to desired channel_type
                        if channel_type == SPCT.BGR:
                            out_sample = img
                        elif channel_type == SPCT.BGR_SHUFFLE:
                            l_rnd_state = np.random.RandomState (sample_rnd_seed)
                            out_sample = np.take (img, l_rnd_state.permutation(img.shape[-1]), axis=-1)
                        elif channel_type == SPCT.BGR_RANDOM_HSV_SHIFT:
                            l_rnd_state = np.random.RandomState (sample_rnd_seed)
                            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
                            h, s, v = cv2.split(hsv)
                            h = (h + l_rnd_state.randint(360) ) % 360
                            s = np.clip ( s + l_rnd_state.random()-0.5, 0, 1 )
                            v = np.clip ( v + l_rnd_state.random()-0.5, 0, 1 )
                            hsv = cv2.merge([h, s, v])
                            out_sample = np.clip( cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR) , 0, 1 )
                        elif channel_type == SPCT.BGR_RANDOM_RGB_LEVELS:
                            l_rnd_state = np.random.RandomState (sample_rnd_seed)
                            np_rnd = l_rnd_state.rand
                            inBlack  = np.array([np_rnd()*0.25    , np_rnd()*0.25    , np_rnd()*0.25], dtype=np.float32)
                            inWhite  = np.array([1.0-np_rnd()*0.25, 1.0-np_rnd()*0.25, 1.0-np_rnd()*0.25], dtype=np.float32)
                            inGamma  = np.array([0.5+np_rnd(), 0.5+np_rnd(), 0.5+np_rnd()], dtype=np.float32)
                            outBlack = np.array([0.0, 0.0, 0.0], dtype=np.float32)
                            outWhite = np.array([1.0, 1.0, 1.0], dtype=np.float32)
                            out_sample = np.clip( (img - inBlack) / (inWhite - inBlack), 0, 1 )
                            out_sample = ( out_sample ** (1/inGamma) ) *  (outWhite - outBlack) + outBlack
                            out_sample = np.clip(out_sample, 0, 1)
                        elif channel_type == SPCT.G:
                            out_sample = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)[...,None]
                        elif channel_type == SPCT.GGG:
                            out_sample = np.repeat ( np.expand_dims(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY),-1), (3,), -1)

                    # Final transformations
                    if not debug:
                        if normalize_tanh:
                            out_sample = np.clip (out_sample * 2.0 - 1.0, -1.0, 1.0)
                    if data_format == "NCHW":
                        out_sample = np.transpose(out_sample, (2,0,1) )
                #else:
                #    img  = imagelib.warp_by_params (params, img,  warp, transform, can_flip=True, border_replicate=True)
                #    img  = cv2.resize( img,  (resolution,resolution), cv2.INTER_CUBIC )
                elif sample_type == SPST.LANDMARKS_ARRAY:
                    l = sample.landmarks
                    l = np.concatenate ( [ np.expand_dims(l[:,0] / w,-1), np.expand_dims(l[:,1] / h,-1) ], -1 )
                    l = np.clip(l, 0.0, 1.0)
                    out_sample = l
                elif sample_type == SPST.PITCH_YAW_ROLL or sample_type == SPST.PITCH_YAW_ROLL_SIGMOID:
                    pitch_yaw_roll = sample.get_pitch_yaw_roll()

                    if params['flip']:
                        yaw = -yaw

                    if sample_type == SPST.PITCH_YAW_ROLL_SIGMOID:
                        pitch = np.clip( (pitch / math.pi) / 2.0 + 0.5, 0, 1)
                        yaw   = np.clip( (yaw / math.pi) / 2.0 + 0.5, 0, 1)
                        roll  = np.clip( (roll / math.pi) / 2.0 + 0.5, 0, 1)

                    out_sample = (pitch, yaw, roll)
                else:
                    raise ValueError ('expected sample_type')

                outputs_sample.append ( out_sample )
            outputs += [outputs_sample]

        return outputs

"""
        close_sample = sample.close_target_list[ np.random.randint(0, len(sample.close_target_list)) ] if sample.close_target_list is not None else None
        close_sample_bgr = close_sample.load_bgr() if close_sample is not None else None

        if debug and close_sample_bgr is not None:
            LandmarksProcessor.draw_landmarks (close_sample_bgr, close_sample.landmarks, (0, 1, 0))
        RANDOM_CLOSE               = 0x00000040, #currently unused
        MORPH_TO_RANDOM_CLOSE      = 0x00000080, #currently unused

if f & SPTF.RANDOM_CLOSE != 0:
                img_type += 10
            elif f & SPTF.MORPH_TO_RANDOM_CLOSE != 0:
                img_type += 20
if img_type >= 10 and img_type <= 19: #RANDOM_CLOSE
    img_type -= 10
    img = close_sample_bgr
    cur_sample = close_sample

elif img_type >= 20 and img_type <= 29: #MORPH_TO_RANDOM_CLOSE
    img_type -= 20
    res = sample.shape[0]

    s_landmarks = sample.landmarks.copy()
    d_landmarks = close_sample.landmarks.copy()
    idxs = list(range(len(s_landmarks)))
    #remove landmarks near boundaries
    for i in idxs[:]:
        s_l = s_landmarks[i]
        d_l = d_landmarks[i]
        if s_l[0] < 5 or s_l[1] < 5 or s_l[0] >= res-5 or s_l[1] >= res-5 or \
            d_l[0] < 5 or d_l[1] < 5 or d_l[0] >= res-5 or d_l[1] >= res-5:
            idxs.remove(i)
    #remove landmarks that close to each other in 5 dist
    for landmarks in [s_landmarks, d_landmarks]:
        for i in idxs[:]:
            s_l = landmarks[i]
            for j in idxs[:]:
                if i == j:
                    continue
                s_l_2 = landmarks[j]
                diff_l = np.abs(s_l - s_l_2)
                if np.sqrt(diff_l.dot(diff_l)) < 5:
                    idxs.remove(i)
                    break
    s_landmarks = s_landmarks[idxs]
    d_landmarks = d_landmarks[idxs]
    s_landmarks = np.concatenate ( [s_landmarks, [ [0,0], [ res // 2, 0], [ res-1, 0], [0, res//2], [res-1, res//2] ,[0,res-1] ,[res//2, res-1] ,[res-1,res-1] ] ] )
    d_landmarks = np.concatenate ( [d_landmarks, [ [0,0], [ res // 2, 0], [ res-1, 0], [0, res//2], [res-1, res//2] ,[0,res-1] ,[res//2, res-1] ,[res-1,res-1] ] ] )
    img = imagelib.morph_by_points (sample_bgr, s_landmarks, d_landmarks)
    cur_sample = close_sample
else:
    """
