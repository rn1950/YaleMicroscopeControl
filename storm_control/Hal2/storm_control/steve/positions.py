#!/usr/bin/env python
"""
Handles the list of positions, including manipulation and 
display in graphics scene.
This is displayed in the mosaic tab, but is technically an 
independent SteveModule() like object.
Hazen 10/18
"""

from PyQt5 import QtCore, QtGui, QtWidgets

import storm_control.steve.coord as coord
import storm_control.steve.steveItems as steveItems


class PositionItem(steveItems.SteveItem):
    """
    These are the square boxes that are used for displaying
    positions of interest
    """
    brush = QtGui.QBrush(QtGui.QColor(255,255,255,0))
    data_type = "position"
    deselected_pen = QtGui.QPen(QtGui.QColor(0,0,255))
    rectangle_size = 1
    selected_pen = QtGui.QPen(QtGui.QColor(255,0,0))

    def __init__(self, a_point = None, **kwds):
        super().__init__(**kwds)

        self.a_point = None
        self.text = None
        self.x_size = coord.umToPix(self.rectangle_size)
        self.y_size = coord.umToPix(self.rectangle_size)
        
        self.graphics_item = QtWidgets.QGraphicsRectItem(0, 0, self.x_size, self.y_size)
        self.graphics_item.setPen(self.deselected_pen)
        self.graphics_item.setBrush(self.brush)
        self.graphics_item.setZValue(1000.0)
        self.setLocation(a_point)

    def getText(self):
        """
        The current position of the object in microns as a text string.
        """
        return self.text

    def movePosition(self, dx_um, dy_um):
        a_point = coord.Point(self.a_point.x_um + dx_um,
                              self.a_point.y_um + dy_um,
                              "um")
        self.setLocation(a_point)

    def saveItem(self, directory, name_no_extension):
        return self.text
        
    def setLocation(self, a_point):
        self.a_point = a_point
        self.text = "{0:.2f},{1:.2f}".format(a_point.x_um, a_point.y_um)
        self.graphics_item.setPos(a_point.x_pix - 0.5 * self.x_size,
                                  a_point.y_pix - 0.5 * self.y_size)

    def setSelected(self, selected):
        """
        If the object is selected, increase it's z value and change the pen
        color, otherwise set the object's z value and pen color back to the
        unselected values.
        """
        if selected:
            self.graphics_item.setZValue(2000.0)
            self.graphics_item.setPen(self.selected_pen)
        else:
            self.graphics_item.setZValue(1000.0)
            self.graphics_item.setPen(self.deselected_pen)


class PositionItemLoader(steveItems.SteveItemLoader):
    """
    Creates a PositionItem from saved data.
    """
    def load(self, directory, x, y):
        return PositionItem(coord.Point(float(x), float(y), "um"))


class Positions(QtWidgets.QListView):
    """
    The position list view, this is what the user actually interacts with.
    This duck types a steveModule.SteveModule() object.
    """
    def __init__(self, item_store = None, parameters = None, **kwds):
        super().__init__(**kwds)

        self.item_store = item_store
        self.mosaic_event_coord = None
        self.step_size = parameters.get("step_size")
        self.title_bar = None

        PositionItem.deselected_pen.setWidth(parameters.get("pen_width"))
        PositionItem.selected_pen.setWidth(parameters.get("pen_width"))
        PositionItem.rectangle_size = parameters.get("rectangle_size")
                
        self.position_list_model = QtGui.QStandardItemModel()
        self.setModel(self.position_list_model)

        self.setToolTip("Use 'a','w','s','d' to move selected position, 'backspace' to delete.")

        # Set mosaic file loader. This handles loading PositionItems from a mosaic file.
        self.item_store.addLoader(PositionItem.data_type, PositionItemLoader())

    def addPosition(self, pos):

        # Add to our item store.
        position_item = PositionItem(pos)
        self.item_store.addItem(position_item)

        # Also add to this views model.
        positions_standard_item = PositionsStandardItem(position_item = position_item)
        self.position_list_model.appendRow(positions_standard_item)

        self.updateTitle()

    def currentChanged(self, current, previous):
        """
        Called when the currently selected item in the list changes.
        """
        previous_item = self.position_list_model.itemFromIndex(previous)
        if isinstance(previous_item, PositionsStandardItem):
            previous_item.setSelected(False)

        current_item = self.position_list_model.itemFromIndex(current)
        if isinstance(current_item, PositionsStandardItem):
            current_item.setSelected(True)

    def currentTabChanged(self, tab_index):

        # Clear the model and re-create from the items as other
        # modules (in other tabs) can also add positions.
        if (tab_index == 0):
            self.position_list_model.clear()
            for elt in self.item_store.itemIterator(item_type = PositionItem):
                positions_standard_item = PositionsStandardItem(position_item = elt)
                self.position_list_model.appendRow(positions_standard_item)

            self.updateTitle()

    def handleRecordPosition(self, ignored):
        self.addPosition(self.mosaic_event_coord)
            
    def keyPressEvent(self, event):
        current_item = self.position_list_model.itemFromIndex(self.currentIndex())
        if isinstance(current_item, PositionsStandardItem):
            #current_pos_item = current_item.getPositionItem()
            which_key = event.key()

            # Delete current item.
            if (which_key == QtCore.Qt.Key_Backspace) or (which_key == QtCore.Qt.Key_Delete):
                self.position_list_model.removeRow(self.currentIndex().row())
                self.item_store.removeItem(current_item.position_item.getItemID())
                self.updateTitle()
                
            elif (which_key == QtCore.Qt.Key_W):
                current_item.movePosition(0.0, -self.step_size)
            elif (which_key == QtCore.Qt.Key_S):
                current_item.movePosition(0.0, self.step_size)
            elif (which_key == QtCore.Qt.Key_A):
                current_item.movePosition(-self.step_size, 0.0)
            elif (which_key == QtCore.Qt.Key_D):
                current_item.movePosition(self.step_size, 0.0)
            else:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def loadPositions(self, filename):
        with open(filename) as fp:
            for line in fp:
                try:
                    [x, y] = line.split(",")
                    self.addPosition(coord.Point(float(x), float(y), "um"))
                except ValueError:
                    pass

    def mosaicLoaded(self):
        # Clear the current positions model. We need to do this otherwise
        # we'll get duplicates of whatever is currently in the model.
        self.position_list_model.clear()        
        for position_item in self.item_store.itemIterator(item_type = PositionItem):
            positions_standard_item = PositionsStandardItem(position_item = position_item)
            self.position_list_model.appendRow(positions_standard_item)

    def savePositions(self, filename):
        with open(filename, "w") as fp:
            for item in self.item_store.itemIterator(item_type = PositionItem):
                fp.write(item.getText() + '\n')

    def setMosaicEventCoord(self, a_coord):
        self.mosaic_event_coord = a_coord
        
    def setTitleBar(self, title_bar):
        self.title_bar = title_bar
        
#    def setSceneItemsVisible(self, visible):
#        ScenePositionItem.visible = visible

    def updateTitle(self):
        if self.title_bar is not None:
            n = self.position_list_model.rowCount()
            if (n == 0):
                self.title_bar.setTitle("Positions")
            else:
                self.title_bar.setTitle("Positions ({0:d} total)".format(n))


class PositionsStandardItem(QtGui.QStandardItem):

    def __init__(self, position_item = None, **kwds):
        super().__init__(**kwds)
        self.position_item = position_item
        self.setText(self.position_item.getText())

    def getPositionItem(self):
        return self.position_item

    def movePosition(self, dx_um, dy_um):
        self.position_item.movePosition(dx_um, dy_um)
        self.setText(self.position_item.getText())

    def setSelected(self, selected):
        self.position_item.setSelected(selected)


#
# The MIT License
#
# Copyright (c) 2018 Zhuang Lab, Harvard University
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