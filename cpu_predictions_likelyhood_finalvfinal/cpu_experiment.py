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
import generate_data
import model_params
import time
import psutil
import subprocess
from subprocess import call
import json
import os
import docker

# Change this to switch from a matplotlib plot to file output.
DATE_FORMAT = "%d/%m/%Y %H:%M"
PLOT = False
SECONDS_PER_STEP = 20
SWARM_CONFIG = {
  "includedFields": [
    {
      "fieldName": "cpu",
      "fieldType": "float",
      "maxValue": 100.0,
      "minValue": 0.0
    }
  ],
  "streamDef": {
    "info": "cpu",
    "version": 1,
    "streams": [
      {
        "info": "cpu.csv",
        "source": "file://cpu.csv",
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
    "predictedField": "cpu"
  },
  "swarmSize": "medium"
}


#medium
global attempt
client = docker.APIClient(base_url='unix://var/run/docker.sock')
Replicas=0
 
def run_adaptation_strategy(attempt, cpu):
  service =  client.inspect_service("web")
  service =  client.inspect_service("web")
  #servicename = service['Spec']['Mode']['Name']
  Replicas = int(service['Spec']['Mode']['Replicated']['Replicas'])
  
  if attempt > 1 and cpu > 70 and Replicas <=20 :
    Replicas *= 2 
    cmd = "docker service scale " + "web" + "=" + str(Replicas)
    res= subprocess.check_output(cmd, shell=True)
    print "Replicas <= 20 Adaptation started", attempt, Replicas, cpu
    time.sleep(300)
  elif attempt < 1 and cpu > 70 and Replicas <= 20:
     
    Replicas += 2 
    cmd = "docker service scale " + "web" + "=" + str(Replicas)
    print "attempt < 1 and cpu > 70 Adaptation started", attempt, Replicas, cpu 
    res= subprocess.check_output(cmd, shell=True)
    time.sleep(300)
  elif attempt > 1 and cpu < 40 and Replicas <= 20 and Replicas >= 1:
    print "Adaptation started", attempt, Replicas, cpu 
    Replicas -= 1 
    if Replicas >=1:
      cmd = "docker service scale " + "web" + "=" + str(Replicas)
      print "Adaptation started", attempt, Replicas, cpu
      res= subprocess.check_output(cmd, shell=True)
      time.sleep(300)
    else:
      Replicas=2

  elif attempt < 1 and cpu < 40 and Replicas >= 1:
    print "Adaptation started", attempt, Replicas, cpu 
    Replicas -= 1
    if Replicas >=1:
      cmd = "docker service scale " + "web" + "=" + str(Replicas)
      print "Adaptation started", attempt, Replicas, cpu
      res= subprocess.check_output(cmd, shell=True)
      time.sleep(300)
    else:
      Replicas=2

  attempt +=1

def swarm_over_data():
  return permutations_runner.runWithConfig(SWARM_CONFIG,
    {'maxWorkers': 8, 'overwrite': True})

def run_sine_experiment():
  input_file = "cpu.csv"
  #generate_data.run(input_file)
  #model_params = swarm_over_data()
  attempt=0
  if PLOT:
    output = NuPICPlotOutput("final_cpu_output")
  else:
    output = NuPICFileOutput("final_cpu_output")
  #model = ModelFactory.create(model_params)
  model = ModelFactory.create(model_params.MODEL_PARAMS)
  model.enableInference({"predictedField": "cpu"})
  adapter=0

  for row in range(1,200):
      s = time.strftime(DATE_FORMAT)
      timestamp = datetime.datetime.strptime(s, DATE_FORMAT)
      #timestamp = datetime.datetime.strptime(row[0], DATE_FORMAT)
      cpu1 = psutil.cpu_percent() 
      cpu = float(cpu1)
      result = model.run({"cpu": cpu})
      
      prediction = result.inferences["multiStepBestPredictions"][1]
      anomalyScore = result.inferences['anomalyScore']
      if anomalyScore > 0.75 : 
        print "anomalyScore is high: " , str(anomalyScore) , " CPU@: ", cpu ," steps: ",str(adapter)
        adapter= adapter + 20
        if adapter >= 300:
          run_adaptation_strategy(attempt, cpu)
          attempt+=1
          adapter = 0
          print "reset timer for new adaptation action"
      else:
          run_adaptation_strategy(attempt, cpu)
          attempt+=1

       
        #with open("/tmp/output.log", "w") as loutput:
          #subprocess.call("docker service scale web=1", shell=True, stdout=loutput, stderr=loutput)
      output.write(timestamp, cpu, prediction, anomalyScore)
      try:
        plt.pause(SECONDS_PER_STEP)
      except:
        pass
      row +=1
  



  output.close()
  #loutput.close()
  # Make sure we wait a total of 2 seconds per iteration.
   



if __name__ == "__main__":
  run_sine_experiment()
