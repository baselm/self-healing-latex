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
import meme_params
import disk_params
import disk_read_params
import net_params
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
SECONDS_PER_STEP = 15
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

#app = Flask(__name__)

'''
@app.route('/webhook', methods=['POST'])
def webhook():
    if request.method == 'POST':
        print "Alert received ######################################################"
        print(request.json)

        run_sine_experiment()
        return '', 200 
    else:
         abort(400)
'''
def run_adaptation_strategy_service(attempt, cpu, anomaly_likelihood):
  cmd=''
  s = time.strftime(DATE_FORMAT)
  timestamp = datetime.datetime.strptime(s, DATE_FORMAT)
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
  
  print 'Replicas != previous_replicas from: ', previous_replicas, " To: ",Replicas, 
  if Replicas != previous_replicas:  
	res= subprocess.check_output(cmd, shell=True)
	resdata = json.dumps(res)
	print res 
	cmd = "docker service update " + "web " + "--label-add=com.docker.swarm.service.desired=" + str(Replicas)
	if 'Service converged' in res:
		result="Service converged"
	  	print "Service converged Successfully From: ", previous_replicas, "To: ", Replicas
	  	reslabel = subprocess.check_output(cmd, shell=True)
	  	lenres = len(reslabel)
	  	writer1.writerow([timestamp,cpu,attempt, previous_replicas , Replicas,result])
	  	attempt +=1
	  	time.sleep(200)
	else:
		writer1.writerow([timestamp,cpu,attempt, previous_replicas , Replicas,"No adaptation"])
		attempt +=1
  else:
  	pass

def swarm_over_data():
  return permutations_runner.runWithConfig(SWARM_CONFIG,
    {'maxWorkers': 8, 'overwrite': True})

def run_adapter():
  
  model = ModelFactory.create(model_params.MODEL_PARAMS)
  model_mem = ModelFactory.create(meme_params.MODEL_PARAMS)
  model_disk = ModelFactory.create(disk_params.MODEL_PARAMS)
  model_disk_read = ModelFactory.create(disk_read_params.MODEL_PARAMS)
  model_net = ModelFactory.create(net_params.MODEL_PARAMS)
  model_mem.enableInference({"predictedField": "mem_active"})
  model_disk.enableInference({"predictedField": "diskwritebytes"})
  model_disk_read.enableInference({"predictedField": "diskreadbytes"})
  model_net.enableInference({"predictedField": "bytes_sent"})
  model.enableInference({"predictedField": "cpu"})
  adapter=0
  attempt=0
  filename ='adapt.csv'
  fileHandle = open(filename,"w")
  writer = csv.writer(fileHandle)
  writer.writerow(["timestamp","cpu", "cpu prediction", "cpu_anomalyscore", "cpu_anamolyLikelihood", "Uc",\
    "mem_used", "mem_prediction", "mem_anomalyScore", "mem_anomalyLikelihood","Um",\
    "disk_write_bytes", "disk_prediction", "disk_anomalyScore","disk_anomalyLikelihood", "Udw",\
    "disk_read_bytes", "disk_read_prediction", "disk_read_anomalyScore","disk_read_anomalyLikelihood", "Udr",\
    "net_s", "net_s_prediction", "net_s_anomalyScore","net_s_anomalyLikelihood", "udnet",\
    "totalUM"])

  for row in range(1, 200):

      s = time.strftime(DATE_FORMAT)
      timestamp = datetime.datetime.strptime(s, DATE_FORMAT)
      net_s = psutil.net_io_counters(pernic=True)['docker0'].bytes_sent
      net_s = float(net_s)/1073741824
      result_net_s = model_net.run({"bytes_sent": net_s})
      net_s_prediction = result_net_s.inferences["multiStepBestPredictions"][1]
      net_s_anomalyScore = result_net_s.inferences['anomalyScore']
      net_s_anomalyLikelihood = anomalyLikelihoodHelper.anomalyProbability(
        net_s, net_s_anomalyScore, timestamp
      )
      print 'net_anomalyScore: ', net_s_anomalyScore, net_s
      udnet = (net_s_anomalyLikelihood* net_s + net_s_anomalyLikelihood*net_s_prediction)/(net_s_anomalyLikelihood+net_s_anomalyLikelihood) 

      print 'udnet', net_s_anomalyLikelihood , udnet
      

      disk = psutil.disk_io_counters(perdisk=False).read_bytes
      disk_read_bytes = float(disk)/1073741824
      result_disk_read = model_disk_read.run({"diskreadbytes": disk_read_bytes})
      disk_read_prediction = result_disk_read.inferences["multiStepBestPredictions"][1]
      disk_read_anomalyScore = result_disk_read.inferences['anomalyScore']
      disk_read_anomalyLikelihood = anomalyLikelihoodHelper.anomalyProbability(
        result_disk_read, disk_read_anomalyScore, timestamp
      )
      print 'disk_read_anomalyScore: ', disk_read_anomalyLikelihood, disk_read_bytes
      udr = (disk_read_anomalyLikelihood* disk_read_bytes + disk_read_anomalyLikelihood*disk_read_prediction)/(disk_read_anomalyLikelihood + disk_read_anomalyLikelihood) 

      print 'udr', disk_read_anomalyLikelihood , udr
      

      disk = psutil.disk_io_counters(perdisk=False).write_bytes
      write_bytes = float(disk)/1073741824
      result_disk = model_disk.run({"diskwritebytes": write_bytes})
      
      disk_prediction = result_disk.inferences["multiStepBestPredictions"][1]
      disk_anomalyScore = result_disk.inferences['anomalyScore']
      disk_anomalyLikelihood = anomalyLikelihoodHelper.anomalyProbability(
        write_bytes, disk_anomalyScore, timestamp
      )
      print 'disk_anomalyLikelihood: ', disk_anomalyLikelihood, write_bytes
      udw = (disk_anomalyLikelihood* write_bytes + disk_anomalyLikelihood*disk_prediction)/(disk_anomalyLikelihood + disk_anomalyLikelihood) 

      print 'Udw', disk_anomalyLikelihood , udw
      
      mem = psutil.virtual_memory().percent 
      mem_used = float(mem)
      result_mem = model_mem.run({"mem_active": mem_used})
      
      mem_prediction = result_mem.inferences["multiStepBestPredictions"][1]
      mem_anomalyScore = result_mem.inferences['anomalyScore']
      mem_anomalyLikelihood = anomalyLikelihoodHelper.anomalyProbability(
        mem_used, mem_anomalyScore, timestamp
      )
      print 'mem_anomalyLikelihood: ', mem_anomalyLikelihood, mem_used
      print 'Um', mem_anomalyLikelihood * mem_used
      
      um = (mem_anomalyLikelihood * mem_used + mem_anomalyLikelihood * mem_prediction)/(mem_anomalyLikelihood + mem_anomalyLikelihood)
      #timestamp = datetime.datetime.strptime(row[0], DATE_FORMAT)
      cpu1 = psutil.cpu_percent(interval=1) 
      cpu = float(cpu1)
      result = model.run({"cpu": cpu})
      
      prediction = result.inferences["multiStepBestPredictions"][1]
      anomalyScore = result.inferences['anomalyScore']
      anomalyLikelihood = anomalyLikelihoodHelper.anomalyProbability(
        cpu, anomalyScore, timestamp
      )
      print 'cpu anomalyLikelihood: ', anomalyLikelihood, cpu
      print 'Uc', anomalyLikelihood * cpu
      uc= (anomalyLikelihood * cpu + prediction * anomalyLikelihood )/(anomalyLikelihood + anomalyLikelihood) 
      print 'totalUM: ', uc
      totalUM = (uc+um+udr+udw+udnet)/(anomalyLikelihood + mem_anomalyLikelihood + disk_anomalyLikelihood \
        + disk_read_anomalyLikelihood+net_s_anomalyLikelihood)

      
      if anomalyScore > 0.75 : 
        print "anomalyScore is high: " , 'anomalyScore: ', str(anomalyScore) , 'anomalyLikelihood: ', anomalyLikelihood, " CPU@: ", cpu ," steps: ",str(adapter)
        adapter= adapter + 20
        if adapter >= 300:
          run_adaptation_strategy_service(attempt, cpu, anomalyLikelihood)
           
          attempt+=1
          adapter = 0
          print "reset timer for new adaptation action"
      else:
          print "anomalyScore is high: " , 'anomalyScore: ', str(anomalyScore) , 'anomalyLikelihood: ', anomalyLikelihood, " CPU@: ", cpu ," steps: ",str(adapter)
          run_adaptation_strategy_service(attempt, cpu,anomalyLikelihood)
          attempt+=1
      
  
      try:
        plt.pause(SECONDS_PER_STEP)
      except:
        pass
      writer.writerow([timestamp, cpu, prediction, anomalyScore, anomalyLikelihood,uc,\
       mem_used, mem_prediction, mem_anomalyScore, mem_anomalyLikelihood, um,\
       write_bytes, disk_prediction, disk_anomalyScore, disk_anomalyLikelihood,udw,\
       disk_read_bytes, disk_read_prediction, disk_read_anomalyScore, disk_read_anomalyLikelihood,udr,\
       net_s, net_s_prediction, net_s_anomalyScore, net_s_anomalyLikelihood, udnet,\
       totalUM])
      row +=1
  fileHandle.close()
  #loutput.close()
  # Make sure we wait a total of 2 seconds per iteration.
   
def run_em_cached_experiment():
   
  model_mem = ModelFactory.create(meme_params.MODEL_PARAMS)

  model.enableInference({"predictedField": "mem_active"})
  for row in range(1,300):
      s = time.strftime(DATE_FORMAT)
      timestamp = datetime.datetime.strptime(s, DATE_FORMAT)
      #timestamp = datetime.datetime.strptime(row[0], DATE_FORMAT)
      mem = psutil.virtual_memory().used 
      mem_used = float(mem)
      result = model.run({"mem_active": mem_used})
      
      prediction = result.inferences["multiStepBestPredictions"][1]
      anomalyScore = result.inferences['anomalyScore']
      anomalyLikelihood = anomalyLikelihoodHelper.anomalyProbability(
        mem_used, anomalyScore, timestamp
      )
      print 'anomalyLikelihood: ', anomalyLikelihood, mem_used
      
 
if __name__ == '__main__':
	filename ='adapt_services.csv'
  	fileHandle1 = open(filename,"w")
  	writer1 = csv.writer(fileHandle1)
  	writer1.writerow(["timestamp","cpu", "steps", "current Replicas","Scaled Replicas", "result"])
  	run_adapter()
  	fileHandle1.close()
    #app.run(host='0.0.0.0', port='5000', debug=True)

   
