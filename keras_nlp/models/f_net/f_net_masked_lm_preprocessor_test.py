import os
import io
import sentencepiece
import tensorflow as tf
from absl.testing import parameterized
from tensorflow import keras

from keras_nlp.models.f_net.f_net_masked_lm_preprocessor import (
    FNetMaskedLMPreprocessor,
)
from keras_nlp.models.f_net.f_net_tokenizer import FNetTokenizer


class FNetMaskedLMPreprocessorTest(tf.test.TestCase, parameterized.TestCase):
    def setUp(self):
        bytes_io = io.BytesIO()
        vocab_data = tf.data.Dataset.from_tensor_slices(
            ["the quick brown fox", "the earth is round"]
        )
        sentencepiece.SentencePieceTrainer.train(
            sentence_iterator=vocab_data.as_numpy_iterator(),
            model_writer=bytes_io,
            vocab_size=12,
            model_type="WORD",
            pad_id=0,
            bos_id=1,
            eos_id=2,
            unk_id=3,
            pad_piece="<pad>",
            unk_piece="<unk>",
            bos_piece="[CLS]",
            eos_piece="[SEP]",
            user_defined_symbols="[MASK]",
        )
        self.proto = bytes_io.getvalue()

        self.preprocessor = FNetMaskedLMPreprocessor(
            tokenizer=FNetTokenizer(proto=self.proto),
            mask_selection_rate=1.0,
            mask_token_rate=1.0,
            random_token_rate=0.0,
            mask_selection_length=4,
            sequence_length=12,
        )

    def test_preprocess_strings(self):
        input_data = "the quick brown fox"

        x, y, sw = self.preprocessor(input_data)
        self.assertAllEqual(
            x["token_ids"], [1, 3, 3, 3, 3, 2, 0, 0, 0, 0, 0, 0]
        )
        self.assertAllEqual(
            x["padding_mask"], [1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0]
        )
        self.assertAllEqual(x["mask_positions"], [1, 2, 3, 4])
        self.assertAllEqual(y, [5, 10, 6, 8])
        self.assertAllEqual(sw, [1.0, 1.0, 1.0, 1.0])

    def test_preprocess_list_of_strings(self):
        input_data = ["the quick brown fox"] * 4

        x, y, sw = self.preprocessor(input_data)
        self.assertAllEqual(
            x["token_ids"], [[1, 3, 3, 3, 3, 2, 0, 0, 0, 0, 0, 0]] * 4
        )
        self.assertAllEqual(
            x["padding_mask"], [[1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0]] * 4
        )
        self.assertAllEqual(x["mask_positions"], [[1, 2, 3, 4]] * 4)
        self.assertAllEqual(y, [[5, 10, 6, 8]] * 4)
        self.assertAllEqual(sw, [[1.0, 1.0, 1.0, 1.0]] * 4)

    def test_preprocess_dataset(self):
        sentences = tf.constant(["the quick brown fox"] * 4)
        ds = tf.data.Dataset.from_tensor_slices(sentences)
        ds = ds.map(self.preprocessor)
        x, y, sw = ds.batch(4).take(1).get_single_element()
        self.assertAllEqual(
            x["token_ids"], [[1, 3, 3, 3, 3, 2, 0, 0, 0, 0, 0, 0]] * 4
        )
        self.assertAllEqual(
            x["padding_mask"], [[1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0]] * 4
        )
        self.assertAllEqual(x["mask_positions"], [[1, 2, 3, 4]] * 4)
        self.assertAllEqual(y, [[5, 10, 6, 8]] * 4)
        self.assertAllEqual(sw, [[1.0, 1.0, 1.0, 1.0]] * 4)

    def test_mask_multiple_sentences(self):
        sentence_one = tf.constant("the quick")
        sentence_two = tf.constant("brown fox")

        x, y, sw = self.preprocessor((sentence_one, sentence_two))
        self.assertAllEqual(
            x["token_ids"], [1, 3, 3, 2, 3, 3, 2, 0, 0, 0, 0, 0]
        )
        self.assertAllEqual(
            x["padding_mask"], [1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
        )
        self.assertAllEqual(x["mask_positions"], [1, 2, 4, 5])
        self.assertAllEqual(y, [5, 10, 6, 8])
        self.assertAllEqual(sw, [1.0, 1.0, 1.0, 1.0])

    def test_no_masking_zero_rate(self):
        no_mask_preprocessor = FNetMaskedLMPreprocessor(
            self.preprocessor.tokenizer,
            mask_selection_rate=0.0,
            mask_selection_length=4,
            sequence_length=12,
        )
        input_data = "the quick brown fox"

        x, y, sw = no_mask_preprocessor(input_data)
        self.assertAllEqual(
            x["token_ids"], [1, 5, 10, 6, 8, 2, 0, 0, 0, 0, 0, 0]
        )
        self.assertAllEqual(
            x["padding_mask"], [1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0]
        )
        self.assertAllEqual(x["mask_positions"], [0, 0, 0, 0])
        self.assertAllEqual(y, [0, 0, 0, 0])
        self.assertAllEqual(sw, [0.0, 0.0, 0.0, 0.0])

    @parameterized.named_parameters(
        ("tf_format", "tf", "model"),
        ("keras_format", "keras_v3", "model.keras"),
    )
    def test_saved_model(self, save_format, filename):
        input_data = tf.constant(["the quick brown fox"])

        inputs = keras.Input(dtype="string", shape=())
        outputs = self.preprocessor(inputs)
        model = keras.Model(inputs, outputs)

        path = os.path.join(self.get_temp_dir(), filename)
        model.save(path, save_format=save_format)

        restored_model = keras.models.load_model(path)
        outputs = model(input_data)[0]["token_ids"]
        restored_outputs = restored_model(input_data)[0]["token_ids"]
        self.assertAllEqual(outputs, restored_outputs)
