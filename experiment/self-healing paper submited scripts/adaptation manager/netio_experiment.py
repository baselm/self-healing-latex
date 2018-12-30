#!/usr/bin/python

# ----------------------------------------------------------------------
# Numenta Platform for Intelligent Computing (NuPIC)
# Copyright (C) 2013, Numenta, Inc.  Unless you have an agreement
# with Numenta, Inc., for a separate license for this software code, the
# following terms and conditions apply:
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see http://www.gnu.org/licenses.
#
# http://numenta.org/licenses/
# ----------------------------------------------------------------------
import csv
from nupic.frameworks.opf.model_factory import ModelFactory
from nupic_output import NuPICFileOutput, NuPICPlotOutput
from nupic.swarming import permutations_runner
import datetime
DATE_FORMAT = "%m/%d/%y %H:%M"

import generate_data

# Change this to switch from a matplotlib plot to file output.
PLOT = True
SWARM_CONFIG = {
  "includedFields": [
    {
      "fieldName": "timestamp",
      "fieldType": "datetime"
    },
    {
      "fieldName": "bytes_sent",
      "fieldType": "float",
      "maxValue": 53.0,
      "minValue": 0.0
    }
  ],
  "streamDef": {
    "info": "bytes_sent",
    "version": 1,
    "streams": [
      {
        "info": "netio.csv",
        "source": "file://netio.csv",
        "columns": [
          "*"
        ]
      }
    ]
  },
  "inferenceType": "TemporalAnomaly",
  "inferenceArgs": {
    "predictionSteps": [
      1
    ],
    "predictedField": "bytes_sent"
  },
  "swarmSize": "small"
}



def swarm_over_data():
  return permutations_runner.runWithConfig(SWARM_CONFIG,
    {'maxWorkers': 8, 'overwrite': True})



def run_sine_experiment():
  input_file = "netio.csv"
  generate_data.run(input_file)
  model_params = swarm_over_data()
  if PLOT:
    output = NuPICPlotOutput("netio_output", show_anomaly_score=True)
  else:
    output = NuPICFileOutput("netio_output", show_anomaly_score=True)
  model = ModelFactory.create(model_params)
  model.enableInference({"predictedField": "bytes_sent"})

  with open(input_file, "rb") as netio_input:
    csv_reader = csv.reader(netio_input)

    # skip header rows
    csv_reader.next()
    csv_reader.next()
    csv_reader.next()

    # the real data
    for row in csv_reader:
     
      timestamp = datetime.datetime.strptime(row[0], DATE_FORMAT)
      bytes_sent = float(row[1])
       
      #netio = float(row[3])
       
      result = model.run({"bytes_sent": bytes_sent})
      output.write(timestamp, bytes_sent, result, prediction_step=1)

  output.close()



if __name__ == "__main__":
  run_sine_experiment()
