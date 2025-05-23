#!/usr/bin/python
#
## @file
#
# Utility for running scripting files for remote control of the HAL-4000 data taking 
# program. The concept is that for each movie that we want to take we create a list 
# of actions that we iterate through. Actions are things like finding sum, recentering 
# the z piezo and taking a movie. Actions can have a delay time associated with them.
#
# Hazen 05/14
#

# Common
import os
import sys
import traceback
import datetime
import time

# XML parsing
#from xml.dom import minidom, Node

# PyQt
from PyQt5 import QtCore, QtGui, QtWidgets

# Debugging
sys.path.append(r'C:\storm_control_git_tracked\YaleMicroscopeControl\storm_control\Hal2')
import storm_control.sc_library.hdebug as hdebug

# General
import storm_control.dave.notifications as notifications
import storm_control.dave.sequenceGenerator as sequenceGenerator
import storm_control.dave.sequenceViewer as sequenceViewer

# Communication
import storm_control.sc_library.tcpClient as tcpClient

# UI
import storm_control.dave.qtdesigner.dave_ui as daveUi

# Parameter loading
import storm_control.sc_library.parameters as params


## CommandEngine
#
# This class handles the execution of commands that can be given to Dave
#
class CommandEngine(QtCore.QObject):
    done = QtCore.pyqtSignal()
    paused = QtCore.pyqtSignal()
    problem = QtCore.pyqtSignal(object)
    warning = QtCore.pyqtSignal(object)
    dave_action = QtCore.pyqtSignal(object)
    
    ## __init__
    #
    #
    @hdebug.debug
    def __init__(self, parent = None):
        QtCore.QObject.__init__(self, parent)

        # Set defaults
        self.command = None
        
        self.test_mode = False
        
        # HAL Client
        self.HALClient = tcpClient.TCPClient(port = 9000,
                                             server_name = "HAL",
                                             verbose = False)
        
        # Kilroy Client
        self.kilroyClient = tcpClient.TCPClient(port = 9500,
                                                server_name = "Kilroy",
                                                verbose = False)
    
    ## abort
    #
    # Aborts the current action (if any).
    #
    @hdebug.debug
    def abort(self):
        self.command.abort()

    ## startCommand
    #
    # Start a command or command sequence
    #
    # @param command The command (DaveAction) to start.
    # @param test_mode (Optional) Run the command in test mode.
    #
    def startCommand(self, command, test_mode = False):
        self.command = command

        # Connect signals.
        self.command.complete_signal.connect(self.handleActionComplete)
        self.command.error_signal.connect(self.handleErrorSignal)
        self.command.warning_signal.connect(self.handleWarningSignal)
        
        # Start command.
        if (self.command.getActionType() == "hal"):
            self.command.start(self.HALClient, test_mode)
        elif (self.command.getActionType() == "kilroy"):
            self.command.start(self.kilroyClient, test_mode)
        elif (self.command.getActionType() == "dave"):
            self.dave_action.emit(self.command.getMessage())
        elif (self.command.getActionType() == "NA"):
            self.command.start(False, test_mode)
        else:
            raise Exception("No TCPClient for " + self.command.getActionType())

    ## handleActionComplete
    #
    # Handle the completion of the previous action
    #
    def handleActionComplete(self, message):
        self.command.cleanUp()
        self.command.complete_signal.disconnect()
        self.command.error_signal.disconnect()
        self.command.warning_signal.disconnect()

        # Configure the command engine to pause after completion of the command sequence
        if self.command.shouldPause() and not message.isTest():
            self.should_pause = True
            self.paused.emit()
        
        self.done.emit()

    ## handleErrorSignal
    #
    # Handle an error signal
    #
    def handleErrorSignal(self, message):
        self.problem.emit(message)
        self.handleActionComplete(message)

    ## handleWarningSignal
    #
    # Handle a warning signal
    #
    def handleWarningSignal(self, message):
        self.warning.emit(message)
        self.handleActionComplete(message)

## Dave
#
# The main window of Dave.
#
class Dave(QtWidgets.QMainWindow):

    ## __init__
    #
    # Creates the window and the UI. Connects the signals. Creates the movie engine.
    #
    # @param parameters A parameters object.
    # @param parent (Optional) The PyQt parent of this object.
    #
    @hdebug.debug
    def __init__(self, parameters, parent = None):
        QtWidgets.QMainWindow.__init__(self, parent)

        # General.
        self.directory = ""
        self.notifier = notifications.Notifier("", "", "", "")
        self.running = False
        self.settings = QtCore.QSettings("storm-control", "dave")
        self.sequence_filename = ""
        self.sequence_validated = False
        self.test_mode = False
        self.skip_warning = False
        self.needs_hal = False
        self.needs_kilroy = False

        # UI setup.
        self.ui = daveUi.Ui_MainWindow()
        self.ui.setupUi(self)

        self.ui.remainingLabel.setText("")
        self.ui.sequenceLabel.setText("")
        self.ui.spaceLabel.setText("")
        self.ui.timeLabel.setText("")

        self.directory = str(self.settings.value("directory", ""))
        self.move(self.settings.value("position", self.pos()))
        self.resize(self.settings.value("size", self.size()))
        
        # Hide widgets
        self.ui.frequencyLabel.hide()
        self.ui.frequencySpinBox.hide()
        self.ui.statusMsgCheckBox.hide()

        # Set icon.
        self.setWindowIcon(QtGui.QIcon("dave.ico"))

        # This is for handling file drops.
        self.ui.centralwidget.__class__.dragEnterEvent = self.dragEnterEvent
        self.ui.centralwidget.__class__.dropEvent = self.dropEvent

        # Connect UI signals.
        self.ui.abortButton.clicked.connect(self.handleAbortButton)
        self.ui.actionNew_Sequence.triggered.connect(self.handleNewSequenceFile)
        self.ui.actionQuit.triggered.connect(self.quit)
        self.ui.actionGenerateXML.triggered.connect(self.handleGenerateXML)
        self.ui.actionSendTestEmail.triggered.connect(self.handleSendTestEmail)
        self.ui.commandSequenceTreeView.update.connect(self.handleDetailsUpdate)
        self.ui.fromAddressLineEdit.textChanged.connect(self.handleNotifierChange)
        self.ui.fromPasswordLineEdit.textChanged.connect(self.handleNotifierChange)
        self.ui.runButton.clicked.connect(self.handleRunButton)
        self.ui.smtpServerLineEdit.textChanged.connect(self.handleNotifierChange)
        self.ui.toAddressLineEdit.textChanged.connect(self.handleNotifierChange)
        self.ui.validateSequenceButton.clicked.connect(self.handleValidateCommandSequence)
        self.ui.commandSequenceTreeView.double_clicked.connect(self.handleDoubleClick)
        self.ui.currentWarnings.double_clicked.connect(self.handleWarningsDoubleClick)
        self.ui.clearWarningsPushButton.clicked.connect(self.handleClearWarnings)
                              
        # Load saved notifications settings.
        self.noti_settings = [[self.ui.fromAddressLineEdit, "from_address"],
                              [self.ui.fromPasswordLineEdit, "from_password"],
                              [self.ui.smtpServerLineEdit, "smtp_server"]]

        for [elt, name] in self.noti_settings:
            elt.setText(self.settings.value(name, ""))

        # Configure command details table.
        #self.ui.commandTableView.setHeaderHidden(True)

        # Set enabled/disabled status
        self.ui.runButton.setEnabled(False)
        self.ui.abortButton.setEnabled(False)
        self.ui.validateSequenceButton.setEnabled(False)
        
        # Initialize progress bar
        self.ui.progressBar.setValue(0)
        self.ui.progressBar.setMinimum(0)
        self.ui.progressBar.setMaximum(1)

        # Command engine.
        self.command_engine = CommandEngine()
        self.command_engine.done.connect(self.handleDone)
        self.command_engine.problem.connect(self.handleProblem)
        self.command_engine.paused.connect(self.handlePauseFromCommandEngine)
        self.command_engine.warning.connect(self.handleWarning)
        self.command_engine.dave_action.connect(self.handleDaveAction)

    ## cleanUp
    #
    # Saves (most of) the notification settings at program exit.
    #
    @hdebug.debug
    def cleanUp(self):
        self.settings.setValue("directory", self.directory)
        self.settings.setValue("position", self.pos())
        self.settings.setValue("size", self.size())

        # Save notification settings.
        for [elt, name] in self.noti_settings:
            self.settings.setValue(name, elt.text())

    ## closeEvent
    #
    # Handles the PyQt close event.
    #
    # @param event A PyQt close event.
    #
    @hdebug.debug
    def closeEvent(self, event):
        self.cleanUp()

    ## dragEnterEvent
    #
    # Handles a PyQt (file) drag enter event.
    #
    # @param event A PyQt drag enter event.
    #
    @hdebug.debug
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    ## dropEvent
    #
    # Handles a PyQt (file) drop event.
    #
    # @param event A PyQt drop event.
    #
    @hdebug.debug
    def dropEvent(self, event):
        for url in event.mimeData().urls():
            self.handleDragDropFile(str(url.toLocalFile()))

    ## handleAbortButton
    #
    # Tells the movie engine to abort the current movie. Resets everything to the initial movie.
    #
    # @param boolean Dummy parameter.
    #
    @hdebug.debug
    def handleAbortButton(self, boolean):
        if not self.test_mode:
            # Force manual conformation of abort
            messageBox = QtWidgets.QMessageBox(parent = self)
            messageBox.setWindowTitle("Abort?")
            messageBox.setText("Are you sure you want to abort the current run?")
            messageBox.setStandardButtons(QtWidgets.QMessageBox.Cancel |
                                          QtWidgets.QMessageBox.Ok)
            messageBox.setDefaultButton(QtWidgets.QMessageBox.Cancel)
            button_ID = messageBox.exec_()

            # Handle response
            if (button_ID == QtWidgets.QMessageBox.Ok):
                abort_text =  "Aborted current run at command " + str(self.ui.commandSequenceTreeView.getCurrentIndex())
                abort_text += ": " + str(self.ui.commandSequenceTreeView.getCurrentItem().getDaveAction().getDescriptor())
                print(abort_text)
                self.ui.commandSequenceTreeView.abort()

                # Set flag to signal reset to handleDone when called.
                if (self.running):
                    self.command_engine.abort()

                # Paused
                else:
                    self.handleDone()

            # Cancel button or window closed event
            else: 
                pass

        else:
            
            self.test_mode = False
            self.sequence_validated = False
            self.ui.commandSequenceTreeView.setTestMode(False)
            
            if (self.running):
                self.command_engine.abort()
            else:
                self.handleDone()

    ## handleClearWarnings
    #
    # Handle requests to clear warnings
    #
    def handleClearWarnings(self, dummy):
        self.ui.currentWarnings.clearWarnings()
                
    ## handleDaveAction
    #
    # Handle a Dave-specific action requested from the command engine.
    # @param message A tcpMessage object used to pass information about the dave-specific dave action.
    #
    def handleDaveAction(self, message):
        if (message.getType() == "Clear Warnings"):
            self.handleClearWarnings(False) #The boolean is a dummy variable
            self.command_engine.handleActionComplete(message) # Send message back to command engine to signal completion
        elif (message.getType() == "Dave Email"): # Handle an email request
            self.notifier.sendMessage(message.getData("subject"), message.getData("body"))
            self.command_engine.handleActionComplete(message) # Return message back to command engine
        else:
            pass # No other options currently        
        
    ## handleDetailsUpdate
    #
    # Update command details table with information about the command.
    #
    # @param details An array containing the command details.
    #
    def handleDetailsUpdate(self, details):
        model = QtGui.QStandardItemModel()
        for row in details:
            items = []
            for column in row:
                item = QtGui.QStandardItem(str(column))
                item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
                items.append(item)
            model.appendRow(items)
        self.ui.commandTableView.setModel(model)

    ## handleDoubleClick
    #
    # Change the current command to the command that has been double clicked.
    #
    # @param item The Dave Action item double clicked.
    #
    def handleDoubleClick(self, item):
        # Confirm that you want to change to the current command
        messageBox = QtWidgets.QMessageBox(parent = self)
        messageBox.setWindowTitle("Change Command?")
        messageBox.setText("Are you sure you want to change the command?")
        messageBox.setStandardButtons(QtWidgets.QMessageBox.Cancel |
                                      QtWidgets.QMessageBox.Ok)
        messageBox.setDefaultButton(QtWidgets.QMessageBox.Cancel)
        button_ID = messageBox.exec_()

        if (button_ID == QtWidgets.QMessageBox.Ok):
            self.ui.commandSequenceTreeView.setCurrentAction(item)    
        else:
            pass

    ## handleDone
    #
    # Handles completion of the current command engine.  
    #
    @hdebug.debug
    def handleDone(self):
        # Handle updating usage information if in test mode
        if self.test_mode:
            self.ui.commandSequenceTreeView.updateEstimates()

        # Increment command to the next valid command / action.
        next_command = self.ui.commandSequenceTreeView.getNextItem()

        # Handle last command in list.
        if next_command is None:
            self.ui.runButton.setText("Start")
            self.ui.runButton.setEnabled(True)
            self.ui.abortButton.setEnabled(False)
            self.ui.validateSequenceButton.setEnabled(True)
            self.ui.commandSequenceTreeView.resetItemIndex()
            
            self.running = False
            if self.test_mode:
                self.sequence_validated = True
                self.test_mode = False
                self.ui.commandSequenceTreeView.setTestMode(False)
                self.updateEstimates()

            # Stop TCP communication
            if self.needs_hal:
                self.command_engine.HALClient.stopCommunication()
            if self.needs_kilroy:
                self.command_engine.kilroyClient.stopCommunication()

        # Continue with next command.
        else: 
            
            # Update time remaining time estimate.
            est_time = self.ui.commandSequenceTreeView.getRemainingTime()
            self.ui.remainingLabel.setText("Time Remaining: " + str(datetime.timedelta(seconds = est_time))[0:8])

            # Check for requested pause.
            if self.running: 
                self.command_engine.startCommand(next_command.getDaveAction(), 
                                                 self.test_mode)
            else: 
                self.handlePause()

        # Update progress bar and current command display.
        self.updateRunStatusDisplay()

    ## handleDropXML
    #
    # Handles a drop event containing a url to an xml file
    #
    # @param file_path Path to file dragged into Dave.
    #
    def handleDragDropFile(self, file_path):
        self.newSequence(file_path)
        
    ## handleGenerateXML
    #
    # Handles Generate from Recipe XML
    #
    # @param boolean Dummy parameter.
    #
    @hdebug.debug
    def handleGenerateXML(self, boolean):
        if self.running:
            QtWidgets.QMessageBox.information(self,
                                              "New Sequence Request",
                                              "Please pause or abort current")
        else:
            recipe_xml_file = QtWidgets.QFileDialog.getOpenFileName(self, 
                                                                    "Open XML File", 
                                                                    self.directory, 
                                                                    "XML (*.xml)")[0]
            if (len(recipe_xml_file)>0):
                try:
                    generated_xml_file = sequenceGenerator.generate(self, recipe_xml_file)
                except:
                    generated_xml_file = None
                    QtWidgets.QMessageBox.information(self,
                                                      "Error Generating XML",
                                                      traceback.format_exc())

                if generated_xml_file is not None:
                    self.directory = os.path.dirname(recipe_xml_file)
                    self.newSequence(generated_xml_file)

    ## handleNewSequenceFile
    #
    # Opens the dialog box that lets the user specify a sequence file.
    #
    # @param boolean Dummy parameter.
    #
    @hdebug.debug
    def handleNewSequenceFile(self, boolean):
        if self.running:
            QtWidgets.QMessageBox.information(self,
                                              "New Sequence Request",
                                              "Please pause or abort current")
        else:
            sequence_filename = QtWidgets.QFileDialog.getOpenFileName(self, "New Sequence", self.directory, "*.xml")[0]
            if sequence_filename:
                self.directory = os.path.dirname(sequence_filename)
                self.newSequence(sequence_filename)
            
    ## handleNotifierChange
    #
    # Handles changes to any of the notification fields of the UI.
    #
    # @param some_text This is a dummy variable that gets the text from the PyQt textChanged signal.
    #
    @hdebug.debug
    def handleNotifierChange(self, some_text):
        self.notifier.setFields(self.ui.smtpServerLineEdit.text(),
                                self.ui.fromAddressLineEdit.text(),
                                self.ui.fromPasswordLineEdit.text(),
                                self.ui.toAddressLineEdit.text())

    ## handlePause
    #
    # Handles a generic pause request. 
    #
    @hdebug.debug
    def handlePause(self):
        self.running = False
        print("\7\7") # Provide audible acknowledgement of pause.

        # Update run button text and status.
        self.ui.runButton.setEnabled(True)
        if not self.ui.commandSequenceTreeView.haveNextItem():
            self.ui.runButton.setText("Restart")
        else:
            self.ui.runButton.setText("Start")

    ## handlePauseFromCommandEngine
    #
    # Handles a pause request from the command engine. 
    #
    @hdebug.debug
    def handlePauseFromCommandEngine(self):
        self.running = False

    ## handleProblem
    #
    # Handles the problem signal from the movie engine. Notifies the operator by e-mail if requested.
    # Displays a dialog box describing the problem.
    #
    # @param message The problem message from the movie engine.
    # @param message_str A informative string regarding the error. Defaults to False.
    #
    @hdebug.debug
    def handleProblem(self, message, message_str = False):
        current_item = self.ui.commandSequenceTreeView.getCurrentItem()
        # Compose message string.
        if not message_str:
            message_str = current_item.getDaveAction().getDescriptor() + "\n" + message.getErrorMessage()

        if not self.test_mode:

            # Pause Dave.
            self.handlePause()

            # Stop TCP communication.
            if self.needs_hal:
                self.command_engine.HALClient.stopCommunication()
            if self.needs_kilroy:
                self.command_engine.kilroyClient.stopCommunication()
            
            # Display errors.
            if (self.ui.errorMsgCheckBox.isChecked()):
                self.notifier.sendMessage("Acquisition Problem",
                                          message_str)
            QtWidgets.QMessageBox.information(self,
                                              "Acquisition Problem",
                                              message_str)

        else: # Test mode
            self.ui.commandSequenceTreeView.setCurrentItemValid(False)
            message_str += "\nSuppress remaining warnings?"
            if not self.skip_warning:
                messageBox = QtWidgets.QMessageBox(parent = self)
                messageBox.setWindowTitle("Invalid Command")
                messageBox.setText(message_str)
                messageBox.setStandardButtons(QtWidgets.QMessageBox.No |
                                              QtWidgets.QMessageBox.YesToAll)
                messageBox.setIcon(QtWidgets.QMessageBox.Warning)
                messageBox.setDefaultButton(QtWidgets.QMessageBox.YesToAll)
                button_ID = messageBox.exec_()
                if button_ID == QtWidgets.QMessageBox.YesToAll:
                    self.skip_warning = True # Skip additional warnings

            print("Invalid command: " + current_item.getDaveAction().getDescriptor())

    ## handleRunButton
    #
    # Handles the run button. If we are running then the text is set to "Pausing.." and the movie engine is told to pause.
    # Otherwise the text is set to "Pause" and the movie engine is told to start.
    #
    # @param boolean Dummy parameter.
    #
    @hdebug.debug
    def handleRunButton(self, boolean):

        # Request pause.
        if (self.running):
            self.ui.runButton.setText("Pausing..")
            self.ui.runButton.setEnabled(False) #Inactivate button until current action is complete
            self.running = False

        # Start
        else: 

            # Confirm run in the presence of invalid commands
            if not self.ui.commandSequenceTreeView.isAllValid():
                messageBox = QtWidgets.QMessageBox(parent = self)
                messageBox.setWindowTitle("Invalid Commands")
                box_text = "There are invalid commands. Are you sure you want to start?\n"
                box_text += "Invalid commands will be skipped."
                messageBox.setText(box_text)
                messageBox.setStandardButtons(QtWidgets.QMessageBox.No |
                                              QtWidgets.QMessageBox.Yes)
                messageBox.setDefaultButton(QtWidgets.QMessageBox.No)
                button_ID = messageBox.exec_()
                if not (button_ID == QtWidgets.QMessageBox.Yes):
                    return

            if not self.sequence_validated:
                messageBox = QtWidgets.QMessageBox(parent = self)
                messageBox.setWindowTitle("Unvalidated Sequence")
                box_text = "The current sequence has not been validated. Are you sure you want to start?\n"
                messageBox.setText(box_text)
                messageBox.setStandardButtons(QtWidgets.QMessageBox.No |
                                              QtWidgets.QMessageBox.Yes)
                messageBox.setDefaultButton(QtWidgets.QMessageBox.No)
                button_ID = messageBox.exec_()
                if not (button_ID == QtWidgets.QMessageBox.Yes):
                    return

            # Start TCP communication
            self.validateAndStartTCP()
            
            self.ui.runButton.setText("Pause")
            self.ui.abortButton.setEnabled(True)
            self.ui.validateSequenceButton.setEnabled(False)
            self.running = True
            self.updateRunStatusDisplay()
            self.command_engine.startCommand(self.ui.commandSequenceTreeView.getCurrentItem().getDaveAction(),
                                             self.test_mode)

    ## handleSendTestEmail
    #
    # Sends a test email based on the current notifier settings. 
    #
    # @param boolean Dummy parameter.
    #
    @hdebug.debug
    def handleSendTestEmail(self, boolean):
        self.notifier.sendMessage("Notifier Test", "Open the pod bay doors, HAL")

    ## handleValidateCommandSequence
    #
    # Start the validation process for a command sequence
    #
    # @param boolean Dummy parameter.
    #
    @hdebug.debug
    def handleValidateCommandSequence(self, boolean):

        # Start Test Run
        if self.validateAndStartTCP():

            # Configure UI
            self.running = True
            self.test_mode = True
            self.ui.runButton.setEnabled(False)
            self.ui.abortButton.setEnabled(True)
            self.ui.validateSequenceButton.setEnabled(False)
            self.skip_warning = False
            
            # Reset command properties.
            self.ui.commandSequenceTreeView.setAllValid(True)
            
            # Place commandSequence into test mode.
            self.ui.commandSequenceTreeView.resetItemIndex()
            self.updateRunStatusDisplay()
            self.ui.commandSequenceTreeView.setTestMode(True)

            # Send first command.
            self.command_engine.startCommand(self.ui.commandSequenceTreeView.getCurrentItem().getDaveAction(),
                                             self.test_mode)

        # Mark all commands as invalid
        else: 
            self.ui.commandSequenceTreeView.setAllValid(False)
            self.updateEstimates()

    ## handleWarning
    #
    # Handles the warning signal from the command engine and determines if Dave should pause
    # @param message The warning message from the movie engine.
    #
    @hdebug.debug
    def handleWarning(self, message):
        # Determine if Dave is in test mode, and use handleProblem if it is
        if self.test_mode:
            self.handleProblem(message)
        else:
            # Get information on the item that generated the warning
            current_item = self.ui.commandSequenceTreeView.getCurrentItem()
            message_str = current_item.getDaveAction().getDescriptor() + "\n" + message.getErrorMessage()
            
            # Generate a warning
            num_warnings = self.ui.currentWarnings.count()
            self.ui.currentWarnings.addWarning(current_item,
                                               message_str = message_str,
                                               descriptor = "Warning " + str(num_warnings+1))

            # Check to see if the number of warnings is larger than the allowed number
            if self.ui.currentWarnings.count() >= self.ui.numWarningsToPause.value():
                # Update Error Message
                message_str = self.ui.currentWarnings.getSummaryMessage()
                print(message_str)
                
                # Handle problem and specify the message
                self.handleProblem(message, message_str = message_str)
            else:
                pass
                # Nothing needs to be done here, Dave should continue running.

    ## handleWarningsDoubleClick
    #
    # Handle a double click on a warnings item
    #
    # @param warning_item The Dave Warnings item double clicked.
    #
    def handleWarningsDoubleClick(self, warning_item):
        # Create a message box to display the warnings information\
        messageBox = QtWidgets.QMessageBox(parent = self)
        messageBox.setWindowTitle("Warning Details")
        warning_message = warning_item.getFullInfo()
        warning_message = warning_message + "\n" + "Would you like to go to this command?"
        messageBox.setText(warning_message)
        messageBox.setStandardButtons(QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Yes)
        messageBox.setDefaultButton(QtWidgets.QMessageBox.No)
        button_ID = messageBox.exec_()

        if (button_ID == QtWidgets.QMessageBox.Yes):
            dave_action_si = warning_item.getDaveActionStandardItem()
            self.ui.commandSequenceTreeView.setCurrentAction(dave_action_si)
        else:
            pass 

    ## newSequence
    #
    # Parses a XML file describing the list of movies to take.
    #
    # @param sequence_filename The name of the XML file.
    #
    @hdebug.debug
    def newSequence(self, sequence_filename):
        if self.running:
            QtWidgets.QMessageBox.information(self,
                                              "New Sequence Request",
                                              "Please pause or abort current run")
        if not self.running:
            model = False
            no_error = True
            try:
                model = sequenceViewer.parseSequenceFile(sequence_filename)

            except:
                try:
                    generated_xml_file = sequenceGenerator.generate(self, sequence_filename)
                    model = sequenceViewer.parseSequenceFile(generated_xml_file)
                except:         
                    QtWidgets.QMessageBox.information(self,
                                                      "Error Loading Sequence",
                                                      traceback.format_exc())
                    no_error = False
            if no_error:
                self.ui.commandSequenceTreeView.setModel(model)
                self.ui.commandSequenceTreeView.setTestMode(False)
                self.skip_warning = False #Enable warnings for invalid commands
                self.sequence_validated = False #Mark sequence as unvalidated
                self.ui.sequenceLabel.setText(sequence_filename)
                self.ui.progressBar.setMaximum(self.ui.commandSequenceTreeView.getNumberItems())
                self.updateRunStatusDisplay()
                
                # Set enabled/disabled status
                self.ui.runButton.setEnabled(True)
                self.ui.runButton.setText("Start")
                self.ui.abortButton.setEnabled(False)
                self.ui.validateSequenceButton.setEnabled(True)

    ## updateEstimates
    #
    # Update disk and duration estimates
    #
    @hdebug.debug
    def updateEstimates(self):
        [est_time, est_space] = self.ui.commandSequenceTreeView.getEstimates()
            
        self.ui.timeLabel.setText("Run Duration: " + str(datetime.timedelta(seconds=est_time))[0:8])
        self.ui.remainingLabel.setText("Time Remaining: " + str(datetime.timedelta(seconds=est_time))[0:8])
        if est_space/2**10 < 1.0: # Less than GB
            self.ui.spaceLabel.setText("Run Size: {0:.2f} MB ".format(est_space))
        elif est_space/2**20 < 1.0: # Less than TB
            self.ui.spaceLabel.setText("Run Size: {0:.2f} GB ".format(est_space/2**10))
        else: # Bigger than 1 TB
            self.ui.spaceLabel.setText("Run Size: {0:.2f} TB ".format(est_space/2**20))

    ## updateRunStatusDisplay
    #
    # Update the GUI.
    #
    def updateRunStatusDisplay(self):
        self.ui.progressBar.setValue(self.ui.commandSequenceTreeView.getCurrentIndex())
        
    ## validateAndStartTCP
    #
    # Determine that the required TCP communications are ready and start them if they are.
    #
    # @return tcp_ready A boolean describing the state of TCP communications
    #
    def validateAndStartTCP(self):
        self.needs_hal = False
        self.needs_kilroy = False
        types = self.ui.commandSequenceTreeView.getActionTypes()
        if ("hal" in types):
            self.needs_hal = True
        if ("kilroy" in types):
            self.needs_kilroy = True

        tcp_ready = True

        # Poll tcp status
        if self.needs_hal:
            if not self.command_engine.HALClient.startCommunication():
                tcp_ready = False
                err_message = "This sequence requires communication with Hal.\n"
                err_message += "Please start Hal!"
                QtWidgets.QMessageBox.information(self,
                                                  "TCP Communication Error",
                                                  err_message)
        if self.needs_kilroy:
            if not self.command_engine.kilroyClient.startCommunication():
                tcp_ready = False
                err_message = "This sequence requires communication with Kilroy.\n"
                err_message += "Please start Kilroy!"
                QtWidgets.QMessageBox.information(self,
                                                  "TCP Communication Error",
                                                  err_message)
        return tcp_ready

    ## quit
    #
    # Handles the quit file action.
    #
    # @param boolean Dummy parameter.
    #
    @hdebug.debug
    def quit(self, boolean):
        self.close()


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    if (len(sys.argv) == 2):
        parameters = params.parameters(sys.argv[1])
    else:
        parameters = params.parameters("settings_default.xml")
        
    # Start logger.
    hdebug.startLogging(parameters.get("directory") + "logs" + os.path.sep, "dave")

    # Load app.
    window = Dave(parameters)
    window.show()
    app.exec_()

#
# The MIT License
#
# Copyright (c) 2013 Zhuang Lab, Harvard University
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
