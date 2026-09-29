def main(n):
    if n <= 0:
        return "Input must be a positive integer."
    elif n == 1:
        return 1
    else:
        return n * main(n - 1)
n = int(input("Enter a positive integer: "))
result = main(n)
print(f"The factorial of {n} is: {result}") 
