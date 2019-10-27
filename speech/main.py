# Copyright 2018 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# [START gae_python37_render_template]
from __future__ import division

import datetime
import requests
import urllib.request
import time
from bs4 import BeautifulSoup
from datetime import date
from flask import Flask, render_template, request
import threading

import re
import sys

from google.cloud import speech
from google.cloud.speech import enums
from google.cloud.speech import types
import pyaudio
from six.moves import queue
from google.cloud import texttospeech

import jinja2
ListeningRN = "Crossroads"

responses = []
RATE = 16000
listening = 0
CHUNK = int(RATE / 10)  # 100ms
app = Flask(__name__)

link = 'https://caldining.berkeley.edu/locations/hours-operation/week-of-nov24'
dining_loc = 'Foothill'

class MicrophoneStream(object):
    """Opens a recording stream as a generator yielding the audio chunks."""
    def __init__(self, rate, chunk):
        self._rate = rate
        self._chunk = chunk

        # Create a thread-safe buffer of audio data
        self._buff = queue.Queue()
        self.closed = True

    def __enter__(self):
        self._audio_interface = pyaudio.PyAudio()
        self._audio_stream = self._audio_interface.open(
            format=pyaudio.paInt16,
            # The API currently only supports 1-channel (mono) audio
            # https://goo.gl/z757pE
            channels=1, rate=self._rate,
            input=True, frames_per_buffer=self._chunk,
            # Run the audio stream asynchronously to fill the buffer object.
            # This is necessary so that the input device's buffer doesn't
            # overflow while the calling thread makes network requests, etc.
            stream_callback=self._fill_buffer,
        )

        self.closed = False

        return self

    def __exit__(self, type, value, traceback):
        self._audio_stream.stop_stream()
        self._audio_stream.close()
        self.closed = True
        # Signal the generator to terminate so that the client's
        # streaming_recognize method will not block the process termination.
        self._buff.put(None)
        self._audio_interface.terminate()

    def _fill_buffer(self, in_data, frame_count, time_info, status_flags):
        """Continuously collect data from the audio stream, into the buffer."""
        self._buff.put(in_data)
        return None, pyaudio.paContinue

    def generator(self):
        while not self.closed:
            # Use a blocking get() to ensure there's at least one chunk of
            # data, and stop iteration if the chunk is None, indicating the
            # end of the audio stream.
            chunk = self._buff.get()
            if chunk is None:
                return
            data = [chunk]

            # Now consume whatever other data's still buffered.
            while True:
                try:
                    chunk = self._buff.get(block=False)
                    if chunk is None:
                        return
                    data.append(chunk)
                except queue.Empty:
                    break

            yield b''.join(data)

#@app.route('/')
@app.route('/handle_data')
def listen_print_loop(responses):
    """Iterates through server responses and prints them.

    The responses passed is a generator that will block until a response
    is provided by the server.

    Each response may contain multiple results, and each result may contain
    multiple alternatives; for details, see https://goo.gl/tjCPAU.  Here we
    print only the transcription for the top alternative of the top result.

    In this case, responses are provided for interim results as well. If the
    response is an interim one, print a line feed at the end of it, to allow
    the next result to overwrite it, until the response is a final one. For the
    final one, print a newline to preserve the finalized transcription.
    """
    num_chars_printed = 0
    global listening
    global ListeningRN
    for response in responses:
        if not response.results:
            continue

        # The `results` list is consecutive. For streaming, we only care about
        # the first result being considered, since once it's `is_final`, it
        # moves on to considering the next utterance.
        result = response.results[0]
        if not result.alternatives:
            continue

        # Display the transcription of the top alternative.
        transcript = result.alternatives[0].transcript

        # Display interim results, but with a carriage return at the end of the
        # line, so subsequent lines will overwrite them.
        #
        # If the previous result was longer than this one, we need to print
        # some extra spaces to overwrite the previous result
        overwrite_chars = ' ' * (num_chars_printed - len(transcript))

        if not result.is_final:
            sys.stdout.write(transcript + overwrite_chars + '\r')
            sys.stdout.flush()

            num_chars_printed = len(transcript)

        else:
            print(transcript + overwrite_chars)
            if re.search(r'\b(oski|)\b', transcript, re.I):
                listening = 1
                print("go bears!")
            if listening:
                if re.search(r'\b(crossroads|croods|crowds)\b',transcript,re.I):
                    listening = 0
                    ListeningRN = "Crossroads"
                if re.search(r'\b(Cafe3|Cafe 3|Cafe)\b',transcript,re.I):
                    listening = 0
                    ListeningRN = "Café 3"
                if re.search(r'\b(Clark Kerr|Clark)\b',transcript,re.I):
                    listening = 0
                    ListeningRN = "Clark Kerr"
                if re.search(r'\b(Foothill)\b',transcript,re.I):
                    listening = 0
                    ListeningRN = "Foothill"
                if re.search(r'\b(Kombini|Convenience Store)\b',transcript,re.I):
                    listening = 0
                    ListeningRN = "Convenience Store"
                if re.search(r'\b(Campus Restaurants)\b',transcript,re.I):
                    listening = 0
                    ListeningRN = "Campus Restaurants"
                    #print crossroads menu

            # Exit recognition if any of the transcribed phrases could be
            # one of our keywords.
            if re.search(r'\b(exit|quit)\b', transcript, re.I):
                print('Exiting..')
                break

            num_chars_printed = 0


def main():
    # See http://g.co/cloud/speech/docs/languages
    # for a list of supported languages.
    language_code = 'en-US'  # a BCP-47 language tag
    global responses
    client = speech.SpeechClient()
    config = types.RecognitionConfig(
        encoding=enums.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=RATE,
        language_code=language_code
        )
    streaming_config = types.StreamingRecognitionConfig(
        config=config,
        interim_results=True)

    with MicrophoneStream(RATE, CHUNK) as stream:
        audio_generator = stream.generator()
        requests = (types.StreamingRecognizeRequest(audio_content=content)
                    for content in audio_generator)

        responses = client.streaming_recognize(streaming_config, requests)

        # Now, put the transcription responses to use.
        listen_print_loop(responses)

@app.route('/favicon.ico')
def favicon():
    return redirect(url_for('static', filename='favicon.ico'))

@app.route('/handle_voice', methods=['POST'])
def handle_voice():
    global ListeningRN
    dplace = request.form['_projectFilepath']
    if dplace:
        ListeningRN = 0
        while not ListeningRN:
            print("not listening to you")
        return render_template('index.html', times=get_cal_dining_schedule(ListeningRN,link),place=ListeningRN)

@app.route('/handle_data', methods=['POST'])
def handle_data(iplace=0):
    if iplace == 0:
        iplace = request.form['projectFilepath']
    # your code
    # return a response
    return render_template('index.html', times=get_cal_dining_schedule(iplace, link), place = iplace)



def get_cal_dining_schedule(user_location, html):
    raw_html = requests.get(html)

    dateobj = date.today()
    today = dateobj.strftime("%A")
    html = BeautifulSoup(raw_html.text, 'html.parser')
    time_table = html.find('p', 'title2', text=user_location).find_next_sibling('table')
    rows = time_table.find_all('tr')
    day_index = 4
    list_of_days = rows[0].find_all('th')
    for i in range(len(list_of_days)):
        if list_of_days[i].text == today:
            day_index = i
            break
    final_menu = []
    for row in rows[1:]:
        if row:
            row_element_list = row.find_all('td')
            final_menu.append(row_element_list[0].text.strip() + ' - ' + row_element_list[day_index].text.strip())
            #print(row.find_all('td')[day_index].text)

    return final_menu


@app.route('/')
def root():
    # For the sake of example, use static information to inflate the template.
    # This will be replaced with real information in later steps.
    dummy_times = [datetime.datetime(2018, 1, 1, 10, 0, 0),
                   datetime.datetime(2018, 1, 2, 10, 30, 0),
                   datetime.datetime(2018, 1, 3, 11, 0, 0),
                   ]

    return render_template('index.html', times=get_cal_dining_schedule(dining_loc, link), place = dining_loc)


if __name__ == '__main__':
    x = threading.Thread(target=main, daemon=True)
    x.start()
    app.run(host='127.0.0.1', port=8080, debug=True)
# [START gae_python37_render_template]
