Console.Write("Enter first number: ");

String first_num = Console.ReadLine();

int num1 = int.Parse(first_num);


Console.Write("Enter second number: ");

String sec_num = Console.ReadLine();

int num2 = int.Parse(sec_num);



Console.Write("Choose operation: ");

String choice = Console.ReadLine();

Console.Write("Result: ");

if (choice == "add")
{

    Console.Write(num1 + num2);

}


else if (choice == "subtract")
{
    Console.Write(num1 - num2);
}

else if (choice == "multiply")
{
    Console.Write(num1 * num2);
}

else if (choice == "divide")
{
    try
    {
        int answer = (num1 / num2);
    }

    catch (DivideByZeroException w)
    {
        Console.Write($"You can't divide by zero cuh. {w.Message}");
    }


}