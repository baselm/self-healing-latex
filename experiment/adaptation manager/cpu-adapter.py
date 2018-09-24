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
import math 
from nupic.algorithms import anomaly_likelihood
from flask import Flask, request, abort



# Change this to switch from a matplotlib plot to file output.
DATE_FORMAT = "%m/%d/%y %H:%M"

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
anomalyLikelihoodHelper = anomaly_likelihood.AnomalyLikelihood()
Replicas=0

app = Flask(__name__)


@app.route('/webhook', methods=['POST'])
def webhook():
    if request.method == 'POST':
        print "Alert received ######################################################"
        print(request.json)

        run_sine_experiment()
        return '', 200 
    else:
         abort(400)

def run_adaptation_strategy(attempt, cpu, anomaly_likelihood):
  cmd=''
  service =  client.inspect_service("web")
  data = json.dumps(service)
  a = json.loads(data)
  ID= a['ID']
  current_replicas =  int(a['Spec']['Mode']['Replicated']['Replicas'])
  print current_replicas
  
  min_replicas    = int(a['Spec']['Labels']['com.docker.swarm.service.min'])
  #print min_replicas
  max_replicas   = int(a['Spec']['Labels']['com.docker.swarm.service.max'])
  #print max_replicas
  desired_replica = int(a['Spec']['Labels']['com.docker.swarm.service.desired'])
  #print desired_replica
  Replicas = int(service['Spec']['Mode']['Replicated']['Replicas'])
  previous_replicas = Replicas
  #print previous_replicas
  if attempt > 1 and cpu > 70 and Replicas <= max_replicas :
    Replicas = int(math.floor(anomaly_likelihood * max_replicas))

    cmd = "docker service scale " + "web" + "=" + str(Replicas)
    print "Replicas <= 20 Adaptation started- ", "attempt: ",attempt, 'Scaled Replicas: ' ,Replicas, 'cpu' ,cpu
     
  elif attempt < 1 and cpu > 70 and Replicas <= max_replicas:
     
    Replicas += 2 
    cmd = "docker service scale " + "web" + "=" + str(Replicas)
    print "First attempt < 1 and cpu > 70 Adaptation started ", "attempt: ",attempt, 'Scaled Replicas: ' ,Replicas, 'cpu' ,cpu
  elif attempt > 1 and cpu < 40 and Replicas <= max_replicas and Replicas > min_replicas :
    print "attempt > 1 and cpu < 40 and Replicas <= 20 Adaptation started- ", "attempt: ",attempt, ' Scaled Replicas: ' ,Replicas, 'cpu' ,cpu
    Replicas -= 1 
    if Replicas > min_replicas and Replicas < max_replicas:
      cmd = "docker service scale " + "web" + "=" + str(Replicas)
      print "attempt > 1 and cpu < 40 and Replicas <= 20 Adaptation started- ", "attempt: ",attempt, 'Scaled Replicas: ' ,Replicas, 'cpu' ,cpu
       
       
    else:
      Replicas=desired_replica

  elif attempt < 1 and cpu < 40 and Replicas > min_replicas:
    print "attempt < 1 and cpu < 40 and Replicas >= 1", "attempt: ",attempt, 'Scaled Replicas: ' ,Replicas, 'cpu' ,cpu
    Replicas -= 1
    if Replicas >=min_replicas:
      cmd = "docker service scale " + "web" + "=" + str(Replicas)
      print "attempt < 1 and cpu < 40 and Replicas >= 1", "attempt: ",attempt, 'Scaled Replicas: ' ,Replicas, 'cpu' ,cpu 
    else:
      Replicas=desired_replica
  print 'Replicas != previous_replicas', Replicas, previous_replicas
  if Replicas != previous_replicas:  
    res= subprocess.check_output(cmd, shell=True)
    resdata = json.dumps(res)
    print res 
    cmd = "docker service update " + "web " + "--label-add=com.docker.swarm.service.desired=" + str(Replicas)
    if 'Service converged' in res:
      print "Service converged Successfully From: ", previous_replicas, "To: ", Replicas
    reslabel = subprocess.check_output(cmd, shell=True)
    attempt +=1
    time.sleep(300)
  else:
    pass

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

  for row in range(1,300):
      s = time.strftime(DATE_FORMAT)
      timestamp = datetime.datetime.strptime(s, DATE_FORMAT)
      #timestamp = datetime.datetime.strptime(row[0], DATE_FORMAT)
      cpu1 = psutil.cpu_percent(interval=1) 
      cpu = float(cpu1)
      result = model.run({"cpu": cpu})
      
      prediction = result.inferences["multiStepBestPredictions"][1]
      anomalyScore = result.inferences['anomalyScore']
      anomalyLikelihood = anomalyLikelihoodHelper.anomalyProbability(
        cpu, anomalyScore, timestamp
      )
      print 'anomalyLikelihood: ', anomalyLikelihood
      
      if anomalyScore > 0.75 : 
        print "anomalyScore is high: " , 'anomalyScore: ', str(anomalyScore) , 'anomalyLikelihood: ', anomalyLikelihood, " CPU@: ", cpu ," steps: ",str(adapter)
        adapter= adapter + 20
        if adapter >= 300:
          run_adaptation_strategy(attempt, cpu, anomalyLikelihood)
          attempt+=1
          adapter = 0
          print "reset timer for new adaptation action"
      else:
          print "anomalyScore is high: " , 'anomalyScore: ', str(anomalyScore) , 'anomalyLikelihood: ', anomalyLikelihood, " CPU@: ", cpu ," steps: ",str(adapter)
          run_adaptation_strategy(attempt, cpu,anomalyLikelihood)
          attempt+=1

       
        #with open("/tmp/output.log", "w") as loutput:
          #subprocess.call("docker service scale web=1", shell=True, stdout=loutput, stderr=loutput)
      #output.write(timestamp, cpu, prediction, anomalyScore)
      try:
        plt.pause(SECONDS_PER_STEP)
      except:
        pass
      row +=1

  #loutput.close()
  # Make sure we wait a total of 2 seconds per iteration.
   

if __name__ == '__main__':
    app.run(host='0.0.0.0', port='5000', debug=True)

   
