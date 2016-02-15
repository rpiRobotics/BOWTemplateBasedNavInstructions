#!/usr/bin/python

import RobotRaconteur as RR
import sys, argparse, select
import copy
import pickle
import os
import numpy as np
import time
import re

template_cmd_servicedef = """
# Service to provide xbox controller like interface to template commands
service TemplateCmd_Interface

option version 0.5

struct XboxControllerInput
    field int32 A
    field int32 B
    field int32 X
    field int32 Y
    field int32 left_thumbstick_X
    field int32 left_thumbstick_Y
    field int32 right_thumbstick_X
    field int32 right_thumbstick_Y
end struct

object TemplateCmd
    property XboxControllerInput controller_input
    function void landmark_sensing(double face_landmark, double near_landmark)
end object

"""


class Node(object):
    def __init__(self, id, actionType=None, action=None, params=None, senseCondition=None, say=None):
        self.id = id
        self.actionType = actionType
        self.action = action
        self.params = params
        self.senseCondition = senseCondition
        self.say = say
        self.children = []

    def __repr__(self, level=0):
        ret = "\t"*level+repr(self.id)+" "+repr(self.actionType)+" "+repr(self.action)+" "+repr(self.params)+" "+repr(self.senseCondition)+" "+repr(self.say)+"\n"
        for child in self.children:
            if level+1 < 10:
                ret += child.__repr__(level+1)
        return ret

    def add_child(self, obj):
        self.children.append(obj)


class TemplateCmd(object):
    """Baxter Template Command Application"""

    def __init__(self):
        """Initialize a TemplateCmd object"""
        self._controller_input = None
        self._text_cmd = '\0'
        self.id = 0
        self.vcurrent = Node(self.id)  # Root Node
        self.G = self.vcurrent
        self.stack = []
        self.default_params = [0, 0, 0, 1]
        self.face_landmark = False
        self.near_landmark = False

    def close(self):
        print "Closing Node"

    # give print and verbal feedback to the user
    def feedback(self, feedback="What should I do next?"):
        speak = "say -v Junior '" + feedback + "'"
        print feedback
        os.system(speak)

    # interface function to get verbal instructions from the user
    def bow_cmd_interface(self):
        resp = "Hello. I am Bow with Navigational Instruction Interface. What can I help you with?"
        self.feedback(resp)
        while self._text_cmd != 'shutdown':
            while sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                self._text_cmd = sys.stdin.readline().strip()

                # send for parsing if it is not 'shutdown'
                if self._text_cmd != 'shutdown':
                    self.parse_instruction(self._text_cmd)

        print self.G.__repr__()
        self._controller_input.B = 1
        resp = "I am exiting now. Thank you and have a great day!"
        self.feedback(resp)

    # check for the given keyword in instruction
    def check_keyword(self, instruction, keyword):
        if instruction.find(keyword) != -1:
            return True
        else:
            return False

    # parse instruction to check for actionType and take appropriate action
    def parse_instruction(self, instruction):
        if self.check_keyword(instruction, "stop"):
            resp = "Ok. Waiting for next instruction."
            self.feedback(resp)
        elif self.check_keyword(instruction, "clear"):
            # clear everything
            self.id = 0
            self.vcurrent = Node(self.id)  # Root Node
            self.G = self.vcurrent
            self.stack = []
            resp = "Cleared all commands. How can I help you today?"
            self.feedback(resp)
        elif self.check_keyword(instruction, "save"):
            filename = instruction.split()[1]
            f = open(filename+'.pckl', 'w')
            pickle.dump(self.G.children[0], f)
            f.close()
            resp = "Saved in " + filename + ". What should I do next?"
            self.feedback(resp)
        elif self.check_keyword(instruction, "load"):
            filename = instruction.split()[1]
            f = open(filename+'.pckl')
            v = pickle.load(f)
            self.vcurrent.add_child(v)
            while v != None:
                self.vcurrent = v
                try:
                    v = v.children[len(v.children)-1]
                except:
                    v = None
            f.close()
            resp = "Loaded " + filename + " at current node. What should I do next?"
            self.feedback(resp)
        elif self.check_keyword(instruction, "execute"):
            resp = "Starting execution"
            self.feedback(resp)
            self.execute_task()
            resp = "Execution complete. What should I do next?"
            self.feedback(resp)
        elif self.check_keyword(instruction, "say"):
            actionType = "Say"
            self.add_speech(actionType, instruction)
        elif self.check_keyword(instruction, "end while") or self.check_keyword(instruction, "end loop"):
            self.end_conditional()
        elif self.check_keyword(instruction, "end if"):
            self.end_conditional()
        elif self.check_keyword(instruction, "do while"):
            actionType = "DoWhile"
            self.begin_conditional(actionType, instruction)
        elif self.check_keyword(instruction, "while"):
            actionType = "While"
            self.begin_conditional(actionType, instruction)
        elif self.check_keyword(instruction, "if"):
            actionType = "If"
            self.begin_conditional(actionType, instruction)
        elif self.check_keyword(instruction, "until"):
            actionType = "DoUntil"
            self.add_actuation(actionType, instruction)
        else:
            actionType = "Do"
            self.add_actuation(actionType, instruction)

    # Create a Node for say command
    def add_speech(self, actionType, instruction):
        say = instruction[4:]
        self.id = self.id + 1
        v = Node(self.id, actionType, None, None, None, say)
        self.vcurrent.add_child(v)
        self.vcurrent = v
        resp = "Ok, I will say that. What should I do next?"
        self.feedback(resp)

    # parse the given instruction to get parameters
    def get_parameters(self, actionType, action, instruction):
        # params = [delX, delY, delZ, velocity]
        params = [0, 0, 0, 1]  # default

        # find all numeric value in instruction
        vals = re.findall("[-+]?\d+[\.]?\d*", instruction)

        if action == "Right":
            params[0] = 1*float(vals[0])
        elif action == "Left":
            params[0] = -1*float(vals[0])
        elif action == "Forward":
            params[1] = 1*float(vals[0])
        elif action == "Backward":
            params[1] = -1*float(vals[0])
        elif action == "Up":
            params[2] = 1*float(vals[0])
        elif action == "Down":
            params[2] = -1*float(vals[0])

        if self.check_keyword(instruction, "velocity"):
            params[3] = float(vals[1])
        return params

    # Create a Node for actuation commands
    def add_actuation(self, actionType, instruction):
        if self.check_keyword(instruction, "forward"):
            action = "Forward"
        elif self.check_keyword(instruction, "backward"):
            action = "Backward"
        elif self.check_keyword(instruction, "right"):
            action = "Right"
        elif self.check_keyword(instruction, "left"):
            action = "Left"
        elif self.check_keyword(instruction, "up"):
            action = "Up"
        elif self.check_keyword(instruction, "down"):
            action = "Down"
        elif self.check_keyword(instruction, "gripper"):
            action = "Gripper"

        params = self.get_parameters(actionType, action, instruction)
        self.id = self.id + 1
        senseCondition = None
        if actionType == "DoUntil":
            senseCondition = self.link_sense_condition(instruction)
        v = Node(self.id, actionType, action, params, senseCondition)
        self.vcurrent.add_child(v)
        self.vcurrent = v
        self.feedback()

    # link for sense condition in case of while, if and do until
    def link_sense_condition(self, instruction):
        return False  # temporary, do something here

    # Creating Branches and Cycles in the Flow of Execution
    # Conditional (while, do while, end while, if, end if) and GoTo
    def begin_conditional(self, actionType, instruction):
        senseCondition = self.link_sense_condition(instruction)
        if actionType != "DoWhile":
            self.id = self.id + 1
            v = Node(self.id, actionType, None, None, senseCondition)
            self.stack.append(v)
            self.vcurrent.add_child(v)
            self.vcurrent = v
        else:
            self.id = self.id + 1
            v = Node(self.id, "Do", "Forward", self.default_params)
            self.stack.append(v)
            self.vcurrent.add_child(v)
            self.vcurrent = v
            v = Node(self.id, actionType, senseCondition)
            self.stack.append(v)
        resp = "What should I do in this " + actionType + " condition?"
        self.feedback(resp)

    def end_conditional(self):
        vconditional = self.stack.pop()
        if vconditional.actionType == "DoWhile":
            self.vcurrent.add_child(vconditional)
            self.vcurrent = vconditional
            self.vcurrent.add_child(self.stack.pop())
        elif vconditional.actionType == "While":
            self.vcurrent.add_child(vconditional)
            self.vcurrent = vconditional
        elif vconditional.actionType == "If":
            self.id = self.id + 1
            v = Node(self.id, "Do", "Forward", self.default_params)
            vconditional.add_child(v)
            self.vcurrent.add_child(v)
            self.vcurrent = v
        resp = vconditional.actionType + " Ended. What should I do next?"
        self.feedback(resp)

    # Executing an action
    def execute_action(self, vcurrent):
        """Convert template commands to their xbox equivalent."""
        if vcurrent.action == "Gripper":
            self._controller_input.Y = 1
        else:
            # fix timing, dimensional accuracy later
            for i in range(int(round(abs(sum(vcurrent.params[0:3]))/vcurrent.params[3]))):
                self._controller_input.left_thumbstick_X = 10000*vcurrent.params[3]*np.sign(vcurrent.params[0])
                self._controller_input.left_thumbstick_Y = 10000*vcurrent.params[3]*np.sign(vcurrent.params[1])
                self._controller_input.right_thumbstick_X = 0
                self._controller_input.right_thumbstick_Y = 10000*vcurrent.params[3]*np.sign(vcurrent.params[2])
                time.sleep(1)

            self._controller_input.left_thumbstick_X = 0
            self._controller_input.left_thumbstick_Y = 0
            self._controller_input.right_thumbstick_X = 0
            self._controller_input.right_thumbstick_Y = 0

    # Executing a Task
    def execute_task(self):
        vcurrent = self.G.children[0]
        while vcurrent != None:
            if vcurrent.actionType == "Do":
                self.execute_action(vcurrent)
                try:
                    vcurrent = vcurrent.children[0]
                except:
                    vcurrent = None
            elif vcurrent.actionType == "DoUntil":
                while self.near_landmark != True:  # temporary
                    self.execute_action(vcurrent)
                try:
                    vcurrent = vcurrent.children[0]
                except:
                    vcurrent = None
            elif vcurrent.actionType == "While" or vcurrent.actionType == "DoWhile" or vcurrent.actionType == "If":
                if self.face_landmark == True:  # temporary
                    try:
                        vcurrent = vcurrent.children[0]
                    except:
                        vcurrent = None
                else:
                    try:
                        vcurrent = vcurrent.children[1]
                    except:
                        vcurrent = None
            elif vcurrent.actionType == "Say":
                speak = vcurrent.say
                self.feedback(speak)
                try:
                    vcurrent = vcurrent.children[0]
                except:
                    vcurrent = None

    def init_xbox_cmd(self):
        if (self._controller_input is None):
            self._controller_input = RR.RobotRaconteurNode.s.NewStructure("TemplateCmd_Interface.XboxControllerInput")

            # initialize structure to zero values
            self._controller_input.A = 0
            self._controller_input.B = 0
            self._controller_input.X = 0
            self._controller_input.Y = 0
            self._controller_input.left_thumbstick_X = 0
            self._controller_input.left_thumbstick_Y = 0
            self._controller_input.right_thumbstick_X = 0
            self._controller_input.right_thumbstick_Y = 0

    @property
    def controller_input(self):
        controller_input = copy.copy(self._controller_input)
        self._controller_input.A = 0
        self._controller_input.B = 0
        self._controller_input.X = 0
        self._controller_input.Y = 0
        return controller_input

    def landmark_sensing(self, face_landmark, near_landmark):
        self.face_landmark = True if face_landmark > 0 else False
        self.near_landmark = True if near_landmark > 0 else False


def main(argv):
    # parse command line arguments
    parser = argparse.ArgumentParser(description='Initialize.')
    parser.add_argument('--port', type=int, default=0,
                        help='TCP port to host service on' + \
                             '(will auto-generate if not specified)')
    args = parser.parse_args(argv)

    # Enable numpy
    RR.RobotRaconteurNode.s.UseNumPy = True

    # Set the Node name
    RR.RobotRaconteurNode.s.NodeName = "TemplateCmdServer"

    # Initialize object
    template_cmd_obj = TemplateCmd()

    # Create transport, register it, and start the server
    print "Registering Transport"
    t = RR.TcpTransport()
    t.EnableNodeAnnounce(RR.IPNodeDiscoveryFlags_NODE_LOCAL |
                         RR.IPNodeDiscoveryFlags_LINK_LOCAL |
                         RR.IPNodeDiscoveryFlags_SITE_LOCAL)

    RR.RobotRaconteurNode.s.RegisterTransport(t)
    t.StartServer(args.port)
    port = args.port
    if (port == 0):
        port = t.GetListenPort()

    # Register the service type and the service
    print "Starting Service"
    RR.RobotRaconteurNode.s.RegisterServiceType(template_cmd_servicedef)
    RR.RobotRaconteurNode.s.RegisterService("TemplateCmd", "TemplateCmd_Interface.TemplateCmd", template_cmd_obj)

    print "Service started, connect via"
    print "tcp://localhost:" + str(port) + "/TemplateCmdServer/TemplateCmd"
    template_cmd_obj.init_xbox_cmd()

    print "Enter 'shutdown' to exit, else enter desired navigational commands..."
    template_cmd_obj.bow_cmd_interface()

    # Safely close
    template_cmd_obj.close()

    # This must be here to prevent segfault
    RR.RobotRaconteurNode.s.Shutdown()


if __name__ == '__main__':
    main(sys.argv[1:])
