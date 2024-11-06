import numpy as np
import soundfile
from axengine import InferenceSession
import onnxruntime as ort
import argparse
import time
from utils import *
import math


def get_args():
    parser = argparse.ArgumentParser(
        prog="melotts",
        description="Run TTS on input sentence"
    )
    parser.add_argument("--sentence", "-s", type=str, required=False, default="爱芯元智半导体股份有限公司，致力于打造世界领先的人工智能感知与边缘计算芯片。服务智慧城市、智能驾驶、机器人的海量普惠的应用")
    parser.add_argument("--wav", "-w", type=str, required=False, default="output.wav")
    parser.add_argument("--sample_rate", "-sr", type=int, required=False, default=44100)
    parser.add_argument("--speed", type=float, required=False, default=1.0)
    parser.add_argument("--lexicon", type=str, required=False, default="../models/lexicon.txt")
    parser.add_argument("--token", type=str, required=False, default="../models/tokens.txt")
    return parser.parse_args()


def audio_numpy_concat(segment_data_list, sr, speed=1.):
    audio_segments = []
    for segment_data in segment_data_list:
        audio_segments += segment_data.reshape(-1).tolist()
        audio_segments += [0] * int((sr * 0.05) / speed)
    audio_segments = np.array(audio_segments).astype(np.float32)
    return audio_segments


def merge_sub_audio(sub_audio_list, pad_size, audio_len):
    # Average pad part
    for i in range(len(sub_audio_list) - 1):
        sub_audio_list[i][-pad_size:] += sub_audio_list[i+1][:pad_size]
        sub_audio_list[i][-pad_size:] /= 2
        if i > 0:
            sub_audio_list[i] = sub_audio_list[i][pad_size:]

    sub_audio = np.concatenate(sub_audio_list, axis=-1)
    return sub_audio[:audio_len]


def main():
    args = get_args()
    sentence = args.sentence
    sample_rate = args.sample_rate
    lexicon_filename = args.lexicon
    token_filename = args.token
    print(f"sentence: {sentence}")
    print(f"sample_rate: {sample_rate}")
    print(f"lexicon: {lexicon_filename}")
    print(f"token: {token_filename}")

    enc_model = "../models/encoder.onnx"
    dec_model = "../models/decoder.axmodel"

    # Split sentence
    sens = split_sentences_zh(sentence)

    # Load lexicon
    lexicon = Lexicon(lexicon_filename, token_filename)

    # Load models
    sess_enc = ort.InferenceSession(enc_model, providers=["CPUExecutionProvider"], sess_options=ort.SessionOptions())
    sess_dec = InferenceSession.load_from_model(dec_model)
    dec_len = sess_dec.get_output_shapes()[0][-1] // 512

    # Load static input
    g = np.fromfile("../models/g.bin", dtype=np.float32).reshape(1, 256, 1)

    # Final wav
    audio_list = []

    # Padding for static decoder shape
    pad_size = max(dec_len // 7, 16)

    # Iterate over splitted sentences
    for n, se in enumerate(sens):
        print(f"\nSentence[{n}]: {se}")
        # Convert sentence to phones and tones
        phones, tones = lexicon.convert(se)

        # Add blank between words
        phones = np.array(intersperse(phones, 0), dtype=np.int32)
        tones = np.array(intersperse(tones, 0), dtype=np.int32)
        phone_len = phones.shape[-1]

        language = np.array([3] * phone_len, dtype=np.int32)

        start = time.time()
        z_p, audio_len = sess_enc.run(None, input_feed={
                                    'phone': phones, 'g': g,
                                    'tone': tones, 'language': language, 
                                    'noise_scale': np.array([0], dtype=np.float32),
                                    'length_scale': np.array([1.0 / args.speed], dtype=np.float32),
                                    'noise_scale_w': np.array([0], dtype=np.float32),
                                    'sdp_ratio': np.array([0], dtype=np.float32)})
        print(f"encoder run take {1000 * (time.time() - start)}ms")
        
        audio_len = audio_len[0]
        actual_size = z_p.shape[-1]
        dec_slice_num = int(np.ceil(actual_size / dec_len)) + 1
        # print(f"origin z_p.shape: {z_p.shape}")
        z_p = np.pad(z_p, pad_width=((0,0),(0,0),(0, dec_slice_num * dec_len - actual_size)), mode="constant", constant_values=0)

        # print(f"phone_len: {phone_len}")
        # print(f"z_p.shape: {z_p.shape}")
        # print(f"dec_slice_num: {dec_slice_num}")
        # print(f"audio_len: {audio_len}")

        i = 0
        sub_audio_list = []
        while (i < actual_size):
            z_p_slice = z_p[..., i : i + dec_len]
            i = i + dec_len - pad_size

            start = time.time()
            audio = sess_dec.run(input_feed={"z_p": z_p_slice,
                                "g": g
                                })["audio"].flatten()
            print(f"Sentence[{n}] Slice[{i}]: decoder run take {1000 * (time.time() - start)}ms")

            sub_audio_list.append(audio)

        sub_audio = merge_sub_audio(sub_audio_list, pad_size * 512, audio_len)
        audio_list.append(sub_audio)

    audio = audio_numpy_concat(audio_list, sr=sample_rate)
    soundfile.write(args.wav, audio, sample_rate)
    print(f"Save to {args.wav}")

if __name__ == "__main__":
    main()
