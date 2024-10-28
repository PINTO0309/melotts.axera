import argparse
# from .melotts.download_utils import load_or_download_config, load_or_download_model
from melotts.tts import TTS
import torch
import onnx, onnxsim
import numpy as np


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-l",
        "--language",
        type=str,
        default="ZH",
        choices=["EN", "FR", "JP", "ES", "ZH", "KR"],
        help="target language for TTS",
    )

    args = parser.parse_args()
    return args


def main():
    language = get_args().language
    config_path = "config.json"
    ckpt_path = "checkpoint.pth"
    phone_len = 64

    tts = TTS(language=language, x_len=phone_len, config_path=config_path, ckpt_path=ckpt_path)

    # speaker_id = 1
    
    # noise_scale = 0.6
    # duration = 3.5

    with torch.no_grad():
        phones = torch.zeros(phone_len, dtype=torch.int32)
        tones = torch.randint(1, 5, size=(phone_len,), dtype=torch.int32)
        lang_ids = torch.zeros(phone_len, dtype=torch.int32) + 1
        noise_scale = torch.FloatTensor([0.667])
        noise_scale_w = torch.FloatTensor([0.8])
        length_scale = torch.FloatTensor([1])
        sdp_ratio = torch.FloatTensor([0])

        # def forward(
        #     self,
        #     x,
        #     x_lengths,
        #     tone,
        #     language,
        #     sid,
        # ):
        inputs = (
            phones, torch.IntTensor([phone_len]), tones, lang_ids, noise_scale, noise_scale_w, length_scale, sdp_ratio
        )

        # Export the model
        torch.onnx.export(tts.model,               # model being run
                        inputs,                         # model input (or a tuple for multiple inputs)
                        "melotts.onnx",   # where to save the model (can be a file or file-like object)
                        export_params=True,        # store the trained parameter weights inside the model file
                        opset_version=16,          # the ONNX version to export the model to
                        do_constant_folding=True,  # whether to execute constant folding for optimization
                        input_names = ['x', 'x_len', 'tone', 'language', 'noise_scale', 'noise_scale_w', 'length_scale', 'sdp_ratio'],   # the model's input names
                        output_names = ['audio', 'audio_len'], # the model's output names
                        )
        sim_model,_ = onnxsim.simplify("melotts.onnx")
        onnx.save(sim_model, "melotts-sim.onnx")
        print("Save to melotts-sim.onnx")


if __name__ == "__main__":
    main()