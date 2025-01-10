from piE861 import piE861

pidev = piE861()
print('about to run macro')
pidev.runZStackMacro(10)


print(pidev.position())
print('macro done')